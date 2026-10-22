"""Seleção explícita entre provedores de WhatsApp configurados no ambiente."""
from __future__ import annotations

from app.agents.base import SendResult
from app.agents.providers.evolution import send_whatsapp_evolution
from app.agents.providers.waha import send_whatsapp_waha
from app.core.config import Settings, get_settings


def selected_whatsapp_provider(settings: Settings | None = None) -> str:
    return (settings or get_settings()).whatsapp_provider.lower()


def whatsapp_provider_configured(settings: Settings | None = None) -> bool:
    current = settings or get_settings()
    provider = selected_whatsapp_provider(current)
    if provider == "waha":
        return bool(current.waha_api_url and current.waha_api_key)
    return bool(current.evolution_api_url and current.evolution_api_key)


async def send_whatsapp_message(
    *, to: str, message: str, idempotency_key: str | None = None
) -> SendResult:
    provider = selected_whatsapp_provider()
    if provider == "waha":
        return await send_whatsapp_waha(
            to=to, message=message, idempotency_key=idempotency_key
        )
    return await send_whatsapp_evolution(
        to=to, message=message, idempotency_key=idempotency_key
    )
