"""Provider real de WhatsApp via Evolution API."""

from __future__ import annotations

import httpx

from app.agents.base import SendResult
from app.agents.providers.errors import classify_provider_exception, format_provider_error
from app.core.config import get_settings


async def send_whatsapp_evolution(
    *, to: str, message: str, idempotency_key: str | None = None
) -> SendResult:
    settings = get_settings()
    if not settings.evolution_api_url:
        return SendResult(
            ok=False,
            channel="whatsapp",
            provider="evolution",
            error="EVOLUTION_API_URL nao configurado",
            outcome="confirmed_failure",
        )
    url = f"{settings.evolution_api_url.rstrip('/')}/message/sendText/{settings.evolution_instance or 'default'}"
    headers = {"apikey": settings.evolution_api_key or ""}
    if idempotency_key:
        # Nem toda versão da Evolution implementa deduplicação nativa, mas o
        # header preserva a correlação e é entendido por gateways compatíveis.
        headers["Idempotency-Key"] = idempotency_key
        headers["X-Correlation-ID"] = idempotency_key
    payload = {"number": to.lstrip("+"), "text": message}
    try:
        async with httpx.AsyncClient(timeout=settings.agents_provider_timeout_seconds) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            external_id = None
            if isinstance(data, dict):
                key = data.get("key")
                external_id = str(key.get("id")) if isinstance(key, dict) and key.get("id") else None
            return SendResult(
                ok=True,
                channel="whatsapp",
                provider="evolution",
                external_id=external_id,
                outcome="confirmed_success",
            )
    except Exception as exc:
        ambiguous, halt_fallback = classify_provider_exception(exc)
        return SendResult(
            ok=False,
            channel="whatsapp",
            provider="evolution",
            error=format_provider_error(exc),
            outcome="unknown" if ambiguous else "confirmed_failure",
            ambiguous=ambiguous,
            halt_fallback=halt_fallback,
        )
