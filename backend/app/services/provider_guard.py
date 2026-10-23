"""Proteções operacionais para envios reais.

O guard usa Redis para funcionar de forma consistente entre múltiplos workers.
Se o Redis estiver indisponível, o envio real é bloqueado: é preferível não
contactar ninguém a enviar sem as proteções de volume e deduplicação esperadas.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass

from app.core.config import get_settings
from app.services.retention_queue import redis_client


@dataclass(frozen=True)
class GuardDecision:
    allowed: bool
    reason: str | None = None
    ambiguous: bool = False
    halt_fallback: bool = False


_PREFIX = "beacon:agents:guard"


def _circuit_key(provider: str) -> str:
    return f"{_PREFIX}:circuit:{provider}"


def _failure_key(provider: str, window: int) -> str:
    return f"{_PREFIX}:failure:{provider}:{window}"


def _backpressure_key(provider: str) -> str:
    return f"{_PREFIX}:backpressure:{provider}"


def _message_key(tenant_id: str, idempotency_key: str) -> str:
    digest = hashlib.sha256(f"{tenant_id}:{idempotency_key}".encode("utf-8")).hexdigest()
    return f"{_PREFIX}:idempotency:{digest}"


def effective_provider_limit(limit: int, *, backpressure_active: bool, factor: float) -> int:
    """Reduz o teto por provedor quando latência alta sinaliza pressão no pool."""
    if limit <= 0 or not backpressure_active:
        return limit
    return max(1, int(limit * factor))


async def claim_message_send(
    *, tenant_id: str, idempotency_key: str, ttl_seconds: int | None = None
) -> bool:
    """Reserva atomicamente uma tentativa de envio usando SET NX entre workers."""
    settings = get_settings()
    ttl = ttl_seconds or settings.agents_idempotency_ttl_seconds
    redis = redis_client()
    try:
        claimed = await redis.set(
            _message_key(tenant_id, idempotency_key),
            "sending",
            ex=ttl,
            nx=True,
        )
        return bool(claimed)
    finally:
        await redis.aclose()


async def finish_message_send(
    *, tenant_id: str, idempotency_key: str, state: str
) -> None:
    """Mantém reservas para sucesso/resultado incerto; libera apenas falhas definitivas."""
    settings = get_settings()
    redis = redis_client()
    try:
        key = _message_key(tenant_id, idempotency_key)
        if state == "failed":
            await redis.delete(key)
        else:
            await redis.set(key, state, ex=settings.agents_idempotency_ttl_seconds)
    finally:
        await redis.aclose()


async def acquire_send_slot(*, tenant_id: str, channel: str, provider: str) -> GuardDecision:
    settings = get_settings()
    if not settings.agents_rate_limit_enabled:
        return GuardDecision(allowed=True)

    redis = redis_client()
    try:
        now = time.time()
        circuit_value = await redis.get(_circuit_key(provider))
        if circuit_value:
            try:
                if float(circuit_value) > now:
                    return GuardDecision(
                        allowed=False,
                        reason=f"circuit breaker aberto para {provider}",
                        halt_fallback=True,
                    )
            except ValueError:
                await redis.delete(_circuit_key(provider))

        window = int(now // 60)
        backpressure_active = bool(await redis.get(_backpressure_key(provider)))
        keys = [
            f"{_PREFIX}:tenant:{tenant_id}:{window}",
            f"{_PREFIX}:channel:{channel}:{window}",
            f"{_PREFIX}:provider:{provider}:{window}",
        ]
        async with redis.pipeline(transaction=True) as pipe:
            for key in keys:
                pipe.incr(key)
                pipe.expire(key, 90)
            values = await pipe.execute()
        counts = [int(values[index]) for index in (0, 2, 4)]
        limits = [
            settings.agents_rate_limit_per_tenant_per_minute,
            settings.agents_rate_limit_per_channel_per_minute,
            effective_provider_limit(
                settings.agents_rate_limit_per_provider_per_minute,
                backpressure_active=backpressure_active,
                factor=settings.agents_provider_backpressure_factor,
            ),
        ]
        labels = ["tenant", "canal", "provider"]
        for count, limit, label in zip(counts, limits, labels):
            if limit > 0 and count > limit:
                return GuardDecision(
                    allowed=False,
                    reason=f"rate limit de {label} excedido",
                    halt_fallback=True,
                )
        return GuardDecision(allowed=True)
    except Exception:
        return GuardDecision(
            allowed=False,
            reason="proteção operacional indisponível (Redis)",
            ambiguous=True,
            halt_fallback=True,
        )
    finally:
        await redis.aclose()


async def record_provider_outcome(
    *,
    provider: str,
    success: bool,
    ambiguous: bool = False,
    latency_seconds: float | None = None,
) -> None:
    """Atualiza circuito e backpressure; latência elevada reduz o teto do provedor."""
    settings = get_settings()
    if not settings.agents_rate_limit_enabled:
        return
    redis = redis_client()
    try:
        if latency_seconds is not None and latency_seconds * 1000 >= settings.agents_provider_latency_threshold_ms:
            # TTL curto cria recuperação automática sem prender o provedor em modo lento.
            await redis.set(
                _backpressure_key(provider),
                "1",
                ex=max(60, settings.agents_circuit_breaker_open_seconds),
            )
        if success:
            await redis.delete(_circuit_key(provider))
            await redis.delete(_failure_key(provider, int(time.time() // 60)))
            return
        if not ambiguous:
            return
        window = int(time.time() // 60)
        key = _failure_key(provider, window)
        async with redis.pipeline(transaction=True) as pipe:
            pipe.incr(key)
            pipe.expire(key, max(90, settings.agents_circuit_breaker_open_seconds))
            result = await pipe.execute()
        failures = int(result[0])
        if failures >= settings.agents_circuit_breaker_failure_threshold:
            expires_at = time.time() + settings.agents_circuit_breaker_open_seconds
            await redis.set(
                _circuit_key(provider),
                str(expires_at),
                ex=settings.agents_circuit_breaker_open_seconds,
            )
    finally:
        await redis.aclose()
