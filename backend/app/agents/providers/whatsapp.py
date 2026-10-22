"""Seleção do provider de WhatsApp configurado para a aplicação."""
from __future__ import annotations

from app.agents.base import SendResult
from app.agents.providers.evolution import send_whatsapp_evolution
from app.agents.providers.waha import send_whatsapp_waha
from app.core.config import get_settings


async def send_whatsapp(
    *, to: str, message: str, idempotency_key: str | None = None
) -> SendResult:
    settings = get_settings()
    if settings.waha_api_url and settings.waha_api_key:
        return await send_whatsapp_waha(
            to=to, message=message, idempotency_key=idempotency_key
        )
    return await send_whatsapp_evolution(
        to=to, message=message, idempotency_key=idempotency_key
    )
