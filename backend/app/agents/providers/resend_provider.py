"""Provider real de e-mail via Resend."""

from __future__ import annotations

import httpx

from app.agents.base import SendResult
from app.agents.providers.errors import classify_provider_exception, format_provider_error
from app.core.config import get_settings


async def send_email_resend(
    *, to: str, subject: str, body: str, idempotency_key: str | None = None,
    api_key_override: str | None = None, from_override: str | None = None
) -> SendResult:
    settings = get_settings()
    key = api_key_override or settings.resend_api_key
    if not key:
        return SendResult(
            ok=False,
            channel="email",
            provider="resend",
            error="RESEND_API_KEY nao configurado",
            outcome="confirmed_failure",
        )
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
        headers["X-Correlation-ID"] = idempotency_key
    payload = {"from": from_override or settings.email_from or "Mira <no-reply@beacon.app>", "to": [to], "subject": subject, "text": body}
    try:
        async with httpx.AsyncClient(timeout=settings.agents_provider_timeout_seconds) as client:
            resp = await client.post("https://api.resend.com/emails", json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return SendResult(
                ok=True,
                channel="email",
                provider="resend",
                external_id=data.get("id") if isinstance(data, dict) else None,
                outcome="confirmed_success",
            )
    except Exception as exc:
        ambiguous, halt_fallback = classify_provider_exception(exc)
        return SendResult(
            ok=False,
            channel="email",
            provider="resend",
            error=format_provider_error(exc),
            outcome="unknown" if ambiguous else "confirmed_failure",
            ambiguous=ambiguous,
            halt_fallback=halt_fallback,
        )
