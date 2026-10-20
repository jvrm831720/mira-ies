"""Provider real de SMS via Twilio — so ativo se as credenciais estiverem configuradas."""

from __future__ import annotations

import httpx

from app.agents.base import SendResult
from app.core.config import get_settings


async def send_sms_twilio(*, to: str, message: str) -> SendResult:
    settings = get_settings()
    if not (settings.twilio_account_sid and settings.twilio_auth_token and settings.twilio_from):
        return SendResult(ok=False, channel="sms", provider="twilio", error="credenciais Twilio nao configuradas")
    url = f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_account_sid}/Messages.json"
    data = {"To": to, "From": settings.twilio_from, "Body": message}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, data=data, auth=(settings.twilio_account_sid, settings.twilio_auth_token))
            resp.raise_for_status()
            body = resp.json()
            return SendResult(ok=True, channel="sms", provider="twilio", external_id=body.get("sid") if isinstance(body, dict) else None)
    except Exception as e:
        return SendResult(ok=False, channel="sms", provider="twilio", error=str(e))
