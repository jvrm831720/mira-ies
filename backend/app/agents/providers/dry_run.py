"""Provider padrao: nao envia nada de verdade, so loga e retorna sucesso simulado."""

from __future__ import annotations

import logging

from app.agents.base import Channel, SendResult

logger = logging.getLogger("beacon.agents.dry_run")


async def dry_run_send(*, channel: Channel, to: str | None, message: str) -> SendResult:
    preview = message[:60] + ("..." if len(message) > 60 else "")
    logger.info("[DRY-RUN][%s] destino=%s preview=%r", channel, to or "N/A", preview)
    return SendResult(ok=True, channel=channel, provider="dry_run", dry_run=True)
