"""Rotas do sistema multiagente de retencao (orquestrador + canais WhatsApp/E-mail/SMS)."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.orchestrator import RetentionOrchestrator, preview_message
from app.core.auth import AuthContext, get_current_tenant
from app.core.config import get_settings
from app.db.session import get_db
from app.models.intervention import InterventionLog
from app.services.retention_queue import enqueue_retention_job, get_job, redis_client

router = APIRouter()

_VALID_CHANNELS = {"whatsapp", "email", "sms"}
_VALID_RISK_LEVELS = {"baixo", "medio", "critico"}
_VALID_STATUSES = {"planned", "sending", "sent", "dry_run", "unknown", "failed", "skipped"}


class RetentionRunRequest(BaseModel):
    batch_id: Optional[str] = None
    campaign_id: Optional[str] = Field(default=None, max_length=120)
    risk_levels: list[str] = Field(default_factory=lambda: ["critico"], max_length=3)
    limit: int = Field(default=50, ge=1, le=500)
    dry_run: Optional[bool] = None
    channels: Optional[list[str]] = Field(default=None, max_length=3)
    prefer_whatsapp_medio: bool = False


@router.post("/agents/retention/run")
async def run_retention(
    body: RetentionRunRequest,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    auth: AuthContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    invalid_levels = [lvl for lvl in body.risk_levels if lvl not in _VALID_RISK_LEVELS]
    if invalid_levels:
        raise HTTPException(status_code=422, detail=f"risk_levels invalidos: {invalid_levels}")
    if body.channels:
        invalid_channels = [c for c in body.channels if c not in _VALID_CHANNELS]
        if invalid_channels:
            raise HTTPException(status_code=422, detail=f"channels invalidos: {invalid_channels}")

    if idempotency_key and len(idempotency_key) > 200:
        raise HTTPException(status_code=422, detail="Idempotency-Key muito longa")

    orchestrator = RetentionOrchestrator(db, tenant_id=auth.tenant_id, prefer_whatsapp_medio=body.prefer_whatsapp_medio)
    return await orchestrator.run(
        risk_levels=body.risk_levels, batch_id=body.batch_id, limit=body.limit,
        dry_run=body.dry_run,
        channels=body.channels,
        campaign_id=body.campaign_id,
        idempotency_key=idempotency_key,
    )


@router.post("/agents/retention/enqueue", status_code=202)
async def enqueue_retention(
    body: RetentionRunRequest,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    auth: AuthContext = Depends(get_current_tenant),
):
    invalid_levels = [lvl for lvl in body.risk_levels if lvl not in _VALID_RISK_LEVELS]
    if invalid_levels:
        raise HTTPException(status_code=422, detail=f"risk_levels invalidos: {invalid_levels}")
    if body.channels:
        invalid_channels = [c for c in body.channels if c not in _VALID_CHANNELS]
        if invalid_channels:
            raise HTTPException(status_code=422, detail=f"channels invalidos: {invalid_channels}")
    if idempotency_key and len(idempotency_key) > 200:
        raise HTTPException(status_code=422, detail="Idempotency-Key muito longa")
    try:
        job = await enqueue_retention_job(
            tenant_id=auth.tenant_id,
            tenant_slug=auth.tenant_slug,
            payload=body.model_dump(),
            idempotency_key=idempotency_key,
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Fila de retenção indisponível") from exc
    return {
        "job_id": job["id"],
        "status": job["status"],
        "deduplicated": job.get("deduplicated", False),
        "created_at": job["created_at"],
    }


@router.get("/agents/retention/jobs/{job_id}")
async def retention_job_status(
    job_id: str,
    auth: AuthContext = Depends(get_current_tenant),
):
    try:
        job = await get_job(job_id, tenant_id=auth.tenant_id)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Fila de retenção indisponível") from exc
    if not job:
        raise HTTPException(status_code=404, detail="Job não encontrado")
    return job


@router.get("/agents/retention/logs")
async def list_retention_logs(
    limit: int = Query(50, ge=1, le=500),
    channel: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    auth: AuthContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    if channel and channel not in _VALID_CHANNELS:
        raise HTTPException(status_code=422, detail=f"channel invalido: {channel}")
    if status and status not in _VALID_STATUSES:
        raise HTTPException(status_code=422, detail=f"status invalido: {status}")

    q = select(InterventionLog).where(InterventionLog.tenant_id == auth.tenant_id)
    if channel:
        q = q.where(InterventionLog.channel == channel)
    if status:
        q = q.where(InterventionLog.status == status)
    q = q.order_by(InterventionLog.created_at.desc()).limit(limit)
    logs = (await db.execute(q)).scalars().all()
    return {
        "count": len(logs),
        "logs": [
            {
                "id": log.id, "student_id": log.student_id, "matricula": log.matricula,
                "channel": log.channel, "risk_level": log.risk_level, "status": log.status,
                "skip_reason": log.skip_reason, "error": log.error, "provider": log.provider,
                "external_id": log.external_id, "correlation_id": log.correlation_id,
                "idempotency_key": log.idempotency_key, "job_id": log.job_id,
                "campaign_id": log.campaign_id, "delivery_status": log.delivery_status,
                "delivery_event_id": log.delivery_event_id,
                "delivery_updated_at": log.delivery_updated_at,
                "message_preview": log.message_preview, "created_at": log.created_at,
            }
            for log in logs
        ],
    }


@router.get("/agents/retention/preview/{student_id}")
async def preview_retention_message(
    student_id: str,
    prefer_whatsapp_medio: bool = Query(False),
    auth: AuthContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await preview_message(
        db, tenant_id=auth.tenant_id, student_id=student_id, prefer_whatsapp_medio=prefer_whatsapp_medio,
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
            "whatsapp": "evolution" if settings.evolution_api_url else "dry_run",
            "email": "resend" if settings.resend_api_key else "dry_run",
            "sms": "twilio" if settings.twilio_account_sid else "dry_run",
        },
        "queue": {
            "name": settings.retention_queue_name,
            "dead_letter_name": settings.retention_dead_letter_queue_name,
            "max_attempts": settings.retention_max_attempts,
            "retry_backoff_seconds": settings.retention_retry_backoff_seconds,
        },
    }


@router.get("/agents/retention/dead-letter")
async def list_retention_dead_letters(
    limit: int = Query(50, ge=1, le=500),
    auth: AuthContext = Depends(get_current_tenant),
):
    """Lista jobs que excederam retries, sempre filtrados pelo tenant."""
    redis = redis_client()
    try:
        job_ids = await redis.lrange(get_settings().retention_dead_letter_queue_name, -limit, -1)
        jobs = []
        for job_id in reversed(job_ids):
            job = await get_job(job_id, tenant_id=auth.tenant_id, redis=redis)
            if job:
                jobs.append(job)
        return {"count": len(jobs), "jobs": jobs}
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Fila dead-letter indisponível") from exc
    finally:
        await redis.aclose()
