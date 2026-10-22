"""Provider real de WhatsApp via WAHA HTTP API."""
from __future__ import annotations

import re

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
            error="WAHA_API_URL e WAHA_API_KEY nao configurados",
            outcome="confirmed_failure",
        )

    digits = re.sub(r"\D", "", to)
    if not digits:
        return SendResult(
            ok=False,
            channel="whatsapp",
            provider="waha",
            error="telefone invalido ou ausente",
            outcome="confirmed_failure",
        )

    base_url = settings.waha_api_url.rstrip("/")
    if base_url.endswith("/api"):
        base_url = base_url[:-4]
    url = f"{base_url}/api/sendText"
    headers = {"X-Api-Key": settings.waha_api_key}
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
        headers["X-Correlation-ID"] = idempotency_key
    payload = {
        "session": settings.waha_session or "default",
        "chatId": f"{digits}@c.us",
        "text": message,
    }

    try:
        async with httpx.AsyncClient(timeout=settings.agents_provider_timeout_seconds) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            try:
                data = response.json()
            except ValueError:
                data = {}
            external_id = None
            if isinstance(data, dict):
                value = data.get("id")
                if value:
                    external_id = str(value)
                key = data.get("key")
                if not external_id and isinstance(key, dict) and key.get("id"):
                    external_id = str(key["id"])
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
