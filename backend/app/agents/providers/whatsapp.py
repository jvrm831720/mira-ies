"""Roteamento configurável entre providers de WhatsApp, com failover seletivo."""
from __future__ import annotations

import logging

from app.agents.base import SendResult
from app.agents.providers.evolution import send_whatsapp_evolution
from app.agents.providers.errors import is_retryable_provider_error
from app.agents.providers.waha import send_whatsapp_waha
from app.core.config import get_settings

logger = logging.getLogger(__name__)


def _configured_provider_names(settings) -> list[str]:
    configured = {
        "waha": bool(settings.waha_api_url and settings.waha_api_key),
        "evolution": bool(settings.evolution_api_url and settings.evolution_api_key),
    }
    order = [name.strip().lower() for name in settings.whatsapp_provider_order.split(",") if name.strip()]
    ordered = [name for name in order if configured.get(name)]
    ordered.extend(name for name, enabled in configured.items() if enabled and name not in ordered)
    return ordered


async def _send_with_provider(
    provider: str, *, to: str, message: str, idempotency_key: str | None
) -> SendResult:
    if provider == "waha":
        return await send_whatsapp_waha(to=to, message=message, idempotency_key=idempotency_key)
    return await send_whatsapp_evolution(to=to, message=message, idempotency_key=idempotency_key)


async def send_whatsapp(
    *, to: str, message: str, idempotency_key: str | None = None, provider: str | None = None
) -> SendResult:
    settings = get_settings()
    if provider is not None:
        return await _send_with_provider(
            provider, to=to, message=message, idempotency_key=idempotency_key
        )

    providers = _configured_provider_names(settings)
    if not providers:
        # Preserve the provider's useful configuration error when none is enabled.
        return await send_whatsapp_evolution(
            to=to, message=message, idempotency_key=idempotency_key
        )

    last_result: SendResult | None = None
    uncertain_failure = False
    for index, name in enumerate(providers):
        result = await _send_with_provider(
            name, to=to, message=message, idempotency_key=idempotency_key
        )
        if result.ok:
            return result
        last_result = result
        retryable = is_retryable_provider_error(result.error)
        if retryable and result.ambiguous:
            uncertain_failure = True
        if index + 1 >= len(providers) or not retryable:
            if uncertain_failure:
                result.ambiguous = True
                result.outcome = "unknown"
                result.halt_fallback = True
            return result
        logger.warning(
            "WhatsApp provider failover after retryable HTTP response",
            extra={"event_name": "provider_failover", "channel": "whatsapp",
                   "from_provider": name, "to_provider": providers[index + 1]},
        )
    return last_result or SendResult(
        ok=False, channel="whatsapp", provider="unknown",
        error="nenhum provider de WhatsApp elegível", outcome="confirmed_failure"
    )
