"""Provider real de e-mail via Resend — so ativo se RESEND_API_KEY estiver configurado."""

from __future__ import annotations

import httpx

from app.agents.base import SendResult
from app.core.config import get_settings


async def send_email_resend(*, to: str, subject: str, body: str) -> SendResult:
    settings = get_settings()
    if not settings.resend_api_key:
        return SendResult(ok=False, channel="email", provider="resend", error="RESEND_API_KEY nao configurado")
    headers = {"Authorization": f"Bearer {settings.resend_api_key}", "Content-Type": "application/json"}
    payload = {"from": settings.email_from or "Mira <no-reply@beacon.app>", "to": [to], "subject": subject, "text": body}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post("https://api.resend.com/emails", json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return SendResult(ok=True, channel="email", provider="resend", external_id=data.get("id") if isinstance(data, dict) else None)
    except Exception as e:
        return SendResult(ok=False, channel="email", provider="resend", error=str(e))
