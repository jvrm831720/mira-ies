"""Agente de canal SMS — dry-run por padrao, Twilio se as credenciais estiverem configuradas."""

from __future__ import annotations

from app.agents.base import MessageContext, SendResult
from app.agents.channels.whatsapp import normalize_phone_br
from app.agents.providers.dry_run import dry_run_send
from app.agents.providers.twilio_provider import send_sms_twilio
from app.agents.templates import render_sms
from app.core.config import get_settings


class SmsAgent:
    channel = "sms"

    def render(self, ctx: MessageContext) -> str:
        return render_sms(ctx)

    async def send(self, ctx: MessageContext, message: str, *, dry_run: bool) -> SendResult:
        phone = normalize_phone_br(ctx.telefone)
        if not phone:
            return SendResult(ok=False, channel="sms", provider="dry_run" if dry_run else "twilio", error="telefone invalido ou ausente")
        settings = get_settings()
        if dry_run or not settings.twilio_account_sid:
            return await dry_run_send(channel="sms", to=phone, message=message)
        return await send_sms_twilio(to=phone, message=message)
