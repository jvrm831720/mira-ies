"""Rotas do sistema multiagente de retencao — núcleo operacional (logs + work-summary).

Nota: módulo mínimo para desbloquear GET /agents/retention/logs.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthContext, get_current_tenant
from app.core.config import get_settings
from app.db.session import get_db
from app.models.intervention import InterventionLog

router = APIRouter()

_VALID_CHANNELS = {"whatsapp", "email", "sms"}
_VALID_STATUSES = {"planned", "sending", "sent", "dry_run", "unknown", "failed", "skipped"}
_VALID_OUTCOMES = {
    "responded",
    "no_response",
    "stayed",
    "dropped",
    "transferred",
    "unknown",
}


def _iso(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _serialize_log(log: InterventionLog) -> dict:
    return {
        "id": log.id,
        "student_id": log.student_id,
        "matricula": log.matricula,
        "channel": log.channel,
        "risk_level": log.risk_level,
        "risk_score": log.risk_score,
        "status": log.status,
        "skip_reason": log.skip_reason,
        "decision_reason": getattr(log, "decision_reason", None),
        "decision_context": getattr(log, "decision_context", None),
        "error": log.error,
        "provider": log.provider,
        "external_id": log.external_id,
        "correlation_id": getattr(log, "correlation_id", None),
        "idempotency_key": getattr(log, "idempotency_key", None),
        "job_id": getattr(log, "job_id", None),
        "campaign_id": getattr(log, "campaign_id", None),
        "delivery_status": getattr(log, "delivery_status", None),
        "delivery_event_id": getattr(log, "delivery_event_id", None),
        "delivery_updated_at": _iso(getattr(log, "delivery_updated_at", None)),
        "message_preview": log.message_preview,
        "outcome": getattr(log, "outcome", None),
        "outcome_at": _iso(getattr(log, "outcome_at", None)),
        "outcome_source": getattr(log, "outcome_source", None),
        "outcome_note": getattr(log, "outcome_note", None),
        "created_at": _iso(log.created_at),
    }


@router.get("/agents/retention/work-summary")
async def retention_work_summary(
    auth: AuthContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    overdue_cutoff = now - timedelta(hours=48)
    base = select(func.count(InterventionLog.id)).where(
        InterventionLog.tenant_id == auth.tenant_id,
    )
    pending = (await db.execute(base.where(InterventionLog.status == "planned"))).scalar_one()
    overdue = (
        await db.execute(
            base.where(
                InterventionLog.status == "planned",
                InterventionLog.created_at < overdue_cutoff,
            )
        )
    ).scalar_one()
    failed = (await db.execute(base.where(InterventionLog.status == "failed"))).scalar_one()
    return {
        "pending": int(pending or 0),
        "overdue_48h": int(overdue or 0),
        "failed": int(failed or 0),
        "overdue_policy_hours": 48,
        "generated_at": now.isoformat(),
        "definition": (
            "Pendentes = decisões planejadas ainda não concluídas; "
            "atrasadas = planejadas há mais de 48 horas. O prazo de 48h é uma política "
            "operacional provisória, não um prazo atribuído individualmente."
        ),
    }


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
                "Logs de retenção indisponíveis. "
                "O schema de intervention_logs pode estar desalinhado do modelo; "
                "reinicie a API após patches de schema ou execute alembic upgrade head."
            ),
        ) from exc


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
            "whatsapp": "dry_run",
            "email": "dry_run",
            "sms": "dry_run",
        },
        "queue": {
            "name": settings.retention_queue_name,
            "dead_letter_name": settings.retention_dead_letter_queue_name,
            "max_attempts": settings.retention_max_attempts,
            "retry_backoff_seconds": settings.retention_retry_backoff_seconds,
        },
        "outcomes": sorted(_VALID_OUTCOMES),
        "module_note": "agents.py restaurado em modo minimo (logs + work-summary)",
    }
