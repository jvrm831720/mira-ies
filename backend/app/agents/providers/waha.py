"""Provedor de WhatsApp via WAHA REST API."""
from __future__ import annotations

import httpx

from app.agents.base import SendResult
from app.agents.providers.errors import classify_provider_exception, format_provider_error
from app.core.config import get_settings


async def send_whatsapp_waha(
    *, to: str, message: str, idempotency_key: str | None = None
) -> SendResult:
    settings = get_settings()
    if not settings.waha_api_url or not settings.waha_api_key:
        return SendResult(
            ok=False,
            channel="whatsapp",
            provider="waha",
            error="WAHA_API_URL ou WAHA_API_KEY nao configurado",
            outcome="confirmed_failure",
        )

    digits = "".join(char for char in to if char.isdigit())
    chat_id = f"{digits}@c.us"
    url = f"{settings.waha_api_url.rstrip('/')}/api/sendText"
    headers = {"X-Api-Key": settings.waha_api_key}
    if idempotency_key:
        # WAHA não documenta deduplicação nativa; mantém correlação para rastreio.
        headers["Idempotency-Key"] = idempotency_key
        headers["X-Correlation-ID"] = idempotency_key
    payload = {
        "session": settings.waha_session,
        "chatId": chat_id,
        "text": message,
    }
    try:
        async with httpx.AsyncClient(timeout=settings.agents_provider_timeout_seconds) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            external_id = None
            if isinstance(data, dict):
                key = data.get("key")
                candidate = data.get("id") or (key.get("id") if isinstance(key, dict) else None)
                if candidate:
                    external_id = str(candidate)
            return SendResult(
                ok=True,
                channel="whatsapp",
                provider="waha",
                external_id=external_id,
                outcome="confirmed_success",
            )
    except Exception as exc:
        ambiguous, halt_fallback = classify_provider_exception(exc)
        return SendResult(
            ok=False,
            channel="whatsapp",
            provider="waha",
            error=format_provider_error(exc),
            outcome="unknown" if ambiguous else "confirmed_failure",
            ambiguous=ambiguous,
            halt_fallback=halt_fallback,
        )
