"""Jobs, send-time and work-summary routes."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.rules import decide_channels
from app.core.auth import AuthContext, get_current_tenant, require_min_role
from app.db.session import get_db
from app.models.intervention import InterventionLog
from app.models.student import Student
from app.services.consent import is_communication_allowed
from app.services.engagement import recommend_send_time
from app.services.retention_queue import (
    RetentionJobLifecycleError,
    get_job,
    transition_retention_job,
)
from app.api.agents_common import router, _VALID_CHANNELS


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


async def _transition_retention_job(job_id: str, action: str, auth: AuthContext):
    try:
        job = await transition_retention_job(job_id, tenant_id=auth.tenant_id, action=action)
    except RetentionJobLifecycleError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Fila de retenção indisponível") from exc
    if not job:
        raise HTTPException(status_code=404, detail="Job não encontrado")
    return job


@router.post("/agents/retention/jobs/{job_id}/pause")
async def pause_retention_job(
    job_id: str,
    auth: AuthContext = Depends(require_min_role("operator")),
):
    """Pause a queued, scheduled or retrying execution before it reaches the worker."""
    return await _transition_retention_job(job_id, "pause", auth)


@router.post("/agents/retention/jobs/{job_id}/resume")
async def resume_retention_job(
    job_id: str,
    auth: AuthContext = Depends(require_min_role("operator")),
):
    """Resume a paused execution by putting it back on the ready queue."""
    return await _transition_retention_job(job_id, "resume", auth)


@router.post("/agents/retention/jobs/{job_id}/cancel")
async def cancel_retention_job(
    job_id: str,
    auth: AuthContext = Depends(require_min_role("operator")),
):
    """Cancel a queued execution or request cancellation for one already running."""
    return await _transition_retention_job(job_id, "cancel", auth)


@router.get("/agents/retention/send-time/{student_id}")
async def get_retention_send_time(
    student_id: str,
    channels: list[str] | None = Query(None),
    auth: AuthContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    if channels:
        invalid_channels = [channel for channel in channels if channel not in _VALID_CHANNELS]
        if invalid_channels:
            raise HTTPException(status_code=422, detail=f"channels inválidos: {invalid_channels}")
    result = await db.execute(
        select(Student).where(Student.id == student_id, Student.tenant_id == auth.tenant_id)
    )
    student = result.scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="Aluno não encontrado.")
    candidates = decide_channels(
        risk_level=student.risk_level or "baixo",
        telefone=student.telefone,
        email=student.email,
    )
    candidates = [
        channel for channel in candidates
        if (not channels or channel in channels)
        and is_communication_allowed(student, channel, "retention")
    ]
    if not candidates:
        raise HTTPException(status_code=422, detail="Aluno sem canal elegível para a finalidade de retenção.")
    return await recommend_send_time(
        db, tenant_id=auth.tenant_id, student_id=student.id, channels=candidates
    )


@router.get("/agents/retention/work-summary")
async def retention_work_summary(
    auth: AuthContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Tenant-scoped operational counts from persisted intervention logs.

    "pending" means a decision persisted with status=planned.
    "overdue" is explicitly a provisional 48-hour SLA for planned decisions,
    not a user-assigned task deadline.
    """
    now = datetime.now(timezone.utc)
    overdue_cutoff = now - timedelta(hours=48)
    base = select(func.count(InterventionLog.id)).where(
        InterventionLog.tenant_id == auth.tenant_id,
    )
    pending = (await db.execute(
        base.where(InterventionLog.status == "planned")
    )).scalar_one()
    overdue = (await db.execute(
        base.where(
            InterventionLog.status == "planned",
            InterventionLog.created_at < overdue_cutoff,
        )
    )).scalar_one()
    failed = (await db.execute(
        base.where(InterventionLog.status == "failed")
    )).scalar_one()
    return {
        "pending": int(pending or 0),
        "overdue_48h": int(overdue or 0),
        "failed": int(failed or 0),
        "overdue_policy_hours": 48,
        "generated_at": now.isoformat(),
        "definition": (
            "Pendentes = decisões planejadas ainda não concluídas; atrasadas = planejadas há mais de 48 horas. "
            "O prazo de 48h é uma política operacional provisória, não um prazo atribuído individualmente."
        ),
    }
