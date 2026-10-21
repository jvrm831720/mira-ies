"""Proteções operacionais para envios reais.

O guard usa Redis para funcionar de forma consistente entre múltiplos workers.
Se o Redis estiver indisponível, o envio real é bloqueado: é preferível não
contactar ninguém a enviar sem as proteções de volume e deduplicação esperadas.
"""

from __future__ import annotations

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
            settings.agents_rate_limit_per_provider_per_minute,
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


async def record_provider_outcome(*, provider: str, success: bool, ambiguous: bool = False) -> None:
    """Atualiza o circuito; somente falhas ambíguas/operacionais contam."""
    settings = get_settings()
    if not settings.agents_rate_limit_enabled:
        return
    redis = redis_client()
    try:
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
