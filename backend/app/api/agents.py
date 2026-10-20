"""Rotas do sistema multiagente de retencao (orquestrador + canais WhatsApp/E-mail/SMS)."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.orchestrator import RetentionOrchestrator, preview_message
from app.core.auth import AuthContext, get_current_tenant
from app.core.config import get_settings
from app.db.session import get_db
from app.models.intervention import InterventionLog

router = APIRouter()

_VALID_CHANNELS = {"whatsapp", "email", "sms"}
_VALID_RISK_LEVELS = {"baixo", "medio", "critico"}
_VALID_STATUSES = {"planned", "sent", "dry_run", "failed", "skipped"}


class RetentionRunRequest(BaseModel):
    batch_id: Optional[str] = None
    risk_levels: list[str] = Field(default_factory=lambda: ["critico"], max_length=3)
    limit: int = Field(default=50, ge=1, le=500)
    dry_run: Optional[bool] = None
    channels: Optional[list[str]] = Field(default=None, max_length=3)
    prefer_whatsapp_medio: bool = False


@router.post("/agents/retention/run")
async def run_retention(
    body: RetentionRunRequest,
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

    orchestrator = RetentionOrchestrator(db, tenant_id=auth.tenant_id, prefer_whatsapp_medio=body.prefer_whatsapp_medio)
    return await orchestrator.run(
        risk_levels=body.risk_levels, batch_id=body.batch_id, limit=body.limit,
        dry_run=body.dry_run, channels=body.channels,
    )


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
    }
