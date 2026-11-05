"""Provider real de SMS via Twilio."""

from __future__ import annotations

import httpx

from app.agents.base import SendResult
from app.agents.providers.errors import classify_provider_exception, format_provider_error
from app.core.config import get_settings


async def send_sms_twilio(
    *, to: str, message: str, idempotency_key: str | None = None,
    status_callback_url: str | None = None,
    account_sid_override: str | None = None,
    auth_token_override: str | None = None,
    from_override: str | None = None
) -> SendResult:
    settings = get_settings()
    sid = account_sid_override or settings.twilio_account_sid
    auth_token = auth_token_override or settings.twilio_auth_token
    sender = from_override or settings.twilio_from
    if not (sid and auth_token and sender):
        return SendResult(
            ok=False,
            channel="sms",
            provider="twilio",
            error="credenciais Twilio nao configuradas",
            outcome="confirmed_failure",
        )
    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
    data = {"To": to, "From": sender, "Body": message}
    if status_callback_url:
        if not status_callback_url.startswith("https://"):
            return SendResult(
                ok=False, channel="sms", provider="twilio",
                error="status_callback_must_be_https",
                outcome="confirmed_failure",
            )
        data["StatusCallback"] = status_callback_url
    headers = {}
    if idempotency_key:
        # Twilio não oferece deduplicação universal para Messages API; o header
        # permite que um gateway/proxy e a auditoria preservem a mesma chave.
        headers["Idempotency-Key"] = idempotency_key
        headers["X-Correlation-ID"] = idempotency_key
    try:
        async with httpx.AsyncClient(timeout=settings.agents_provider_timeout_seconds) as client:
            resp = await client.post(
                url,
                data=data,
                headers=headers,
                auth=(sid, auth_token),
            )
            resp.raise_for_status()
            body = resp.json()
            return SendResult(
                ok=True,
                channel="sms",
                provider="twilio",
                external_id=body.get("sid") if isinstance(body, dict) else None,
                outcome="confirmed_success",
            )
    except Exception as exc:
        ambiguous, halt_fallback = classify_provider_exception(exc)
        return SendResult(
            ok=False,
            channel="sms",
            provider="twilio",
            error=format_provider_error(exc),
            outcome="unknown" if ambiguous else "confirmed_failure",
            ambiguous=ambiguous,
            halt_fallback=halt_fallback,
        )
