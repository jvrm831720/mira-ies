"""Agente de canal WhatsApp — dry-run por padrao, Evolution API se EVOLUTION_API_URL configurado."""

from __future__ import annotations

import re

from app.agents.base import MessageContext, SendResult
from app.agents.providers.dry_run import dry_run_send
from app.agents.providers.whatsapp_dispatch import (
    selected_whatsapp_provider,
    send_whatsapp_message,
    whatsapp_provider_configured,
)
from app.agents.templates import render_whatsapp
from app.core.config import get_settings


def normalize_phone_br(raw: str | None) -> str | None:
    """Normaliza best-effort para E.164 (+55...). Retorna None se nao parecer um numero valido."""
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return None
    if digits.startswith("55") and len(digits) in (12, 13):
        return f"+{digits}"
    if len(digits) in (10, 11):
        return f"+55{digits}"
    if raw.strip().startswith("+") and len(digits) >= 10:
        return f"+{digits}"
    return None


class WhatsAppAgent:
    channel = "whatsapp"

    def render(self, ctx: MessageContext) -> str:
        return render_whatsapp(ctx)

    async def send(
        self,
        ctx: MessageContext,
        message: str,
        *,
        dry_run: bool,
        idempotency_key: str | None = None,
    ) -> SendResult:
        phone = normalize_phone_br(ctx.telefone)
        if not phone:
            return SendResult(
                ok=False,
                channel="whatsapp",
                provider="dry_run" if dry_run else selected_whatsapp_provider(),
                error="telefone invalido ou ausente",
                outcome="confirmed_failure",
            )
        settings = get_settings()
        if dry_run or not whatsapp_provider_configured(settings):
            return await dry_run_send(channel="whatsapp", to=phone, message=message)
        return await send_whatsapp_message(
            to=phone, message=message, idempotency_key=idempotency_key
        )
