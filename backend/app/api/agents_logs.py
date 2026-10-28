"""Retention logs, outcome, preview and agents status routes."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthContext, get_current_tenant, require_min_role
from app.core.config import get_settings
from app.db.session import get_db
from app.models.intervention import InterventionLog
from app.services.engagement import record_engagement_event
from app.agents.orchestrator import preview_message
from app.api.agents_common import (
    router,
    _VALID_CHANNELS,
    _VALID_STATUSES,
    _VALID_OUTCOMES,
    _serialize_log,
    OutcomeUpdateRequest,
)


@router.get("/agents/retention/logs")
async def list_retention_logs(
    limit: int = Query(50, ge=1, le=500),
    channel: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    student_id: Optional[str] = Query(None),
    outcome: Optional[str] = Query(None),
    auth: AuthContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    if channel and channel not in _VALID_CHANNELS:
        raise HTTPException(status_code=422, detail=f"channel invalido: {channel}")
    if status and status not in _VALID_STATUSES:
        raise HTTPException(status_code=422, detail=f"status invalido: {status}")
    if outcome and outcome not in _VALID_OUTCOMES and outcome != "pending":
        raise HTTPException(status_code=422, detail=f"outcome invalido: {outcome}")

    q = select(InterventionLog).where(InterventionLog.tenant_id == auth.tenant_id)
    if channel:
        q = q.where(InterventionLog.channel == channel)
    if status:
        q = q.where(InterventionLog.status == status)
    if student_id:
        q = q.where(InterventionLog.student_id == student_id)
    if outcome == "pending":
        q = q.where(InterventionLog.outcome.is_(None))
    elif outcome:
        q = q.where(InterventionLog.outcome == outcome)
    q = q.order_by(InterventionLog.created_at.desc()).limit(limit)
    try:
        logs = (await db.execute(q)).scalars().all()
        return {"count": len(logs), "logs": [_serialize_log(log) for log in logs]}
    except Exception as exc:
        import logging

        logging.getLogger(__name__).exception(
            "list_retention_logs failed tenant=%s err=%s",
            auth.tenant_id,
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=503,
            detail=(
                "Logs de retenção indisponíveis (schema ou consulta). "
                "Verifique intervention_logs e reinicie a API."
            ),
        ) from exc


@router.patch("/agents/retention/logs/{log_id}/outcome")
async def set_retention_outcome(
    log_id: str,
    body: OutcomeUpdateRequest,
    auth: AuthContext = Depends(require_min_role("operator")),
    db: AsyncSession = Depends(get_db),
):
    """Fecha o ciclo de aprendizado: registra o desfecho da intervenção."""
    result = await db.execute(
        select(InterventionLog).where(
            InterventionLog.id == log_id,
            InterventionLog.tenant_id == auth.tenant_id,
        )
    )
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail="Evento de retenção não encontrado")

    occurred_at = datetime.now(timezone.utc)
    log.outcome = body.outcome
    log.outcome_at = occurred_at
    log.outcome_source = body.source
    log.outcome_note = body.note
    if body.outcome in {"responded", "no_response"} and log.student_id:
        await record_engagement_event(
            db,
            tenant_id=auth.tenant_id,
            student_id=log.student_id,
            event_key=f"outcome:{log.id}:{body.outcome}:{occurred_at.isoformat()}",
            event_type="replied" if body.outcome == "responded" else "no_response",
            channel=log.channel,
            source=f"outcome_{body.source}",
            intervention_log_id=log.id,
            occurred_at=occurred_at,
            event_metadata={"outcome_source": body.source},
        )
    else:
        await db.commit()
    await db.refresh(log)
    return _serialize_log(log)


@router.get("/agents/retention/preview/{student_id}")
async def preview_retention_message(
    student_id: str,
    prefer_whatsapp_medio: bool = Query(False),
    auth: AuthContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await preview_message(
        db,
        tenant_id=auth.tenant_id,
        student_id=student_id,
        prefer_whatsapp_medio=prefer_whatsapp_medio,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Aluno nao encontrado")
    return result


@router.get("/agents/status")
async def agents_status(auth: AuthContext = Depends(get_current_tenant)):
    settings = get_settings()
    return {
        "dry_run_default": settings.agents_dry_run_default,
        "anti_spam": {
            "min_hours_between_contact": settings.agents_min_hours_between_contact,
            "max_contacts_per_week": settings.agents_max_contacts_per_week,
        },
        "providers": {
            "whatsapp": "waha" if settings.waha_api_url and settings.waha_api_key else (
                "evolution" if settings.evolution_api_url and settings.evolution_api_key else "dry_run"
            ),
            "email": "resend" if settings.resend_api_key else "dry_run",
            "sms": "twilio" if settings.twilio_account_sid else "dry_run",
        },
        "queue": {
            "name": settings.retention_queue_name,
            "dead_letter_name": settings.retention_dead_letter_queue_name,
            "max_attempts": settings.retention_max_attempts,
            "retry_backoff_seconds": settings.retention_retry_backoff_seconds,
        },
        "outcomes": sorted(_VALID_OUTCOMES),
    }
