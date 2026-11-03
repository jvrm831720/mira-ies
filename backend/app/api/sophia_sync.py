"""Tenant-scoped SophiA sync job API."""
from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthContext, require_min_role
from app.db.session import get_db
from app.models.sophia_connection import TenantSophiaConnection
from app.models.sophia_sync import SophiaSyncJob, SophiaSyncJobEvent, SophiaStudentResource

router = APIRouter(prefix="/integrations/sophia/sync", tags=["SophiA Sync"])


class SophiaSyncRequest(BaseModel):
    student_ids: list[str] = Field(default_factory=list, max_length=5000)
    idempotency_key: str = Field(min_length=8, max_length=160)


async def _tenant(db: AsyncSession, tenant_id: str) -> None:
    await db.execute(text("SELECT set_config('app.tenant_id', :tenant_id, true)"), {"tenant_id": tenant_id})


@router.post("/jobs", status_code=202)
async def enqueue_sophia_sync(
    body: SophiaSyncRequest,
    auth: AuthContext = Depends(require_min_role("coordinator")),
    db: AsyncSession = Depends(get_db),
):
    await _tenant(db, auth.tenant_id)
    connection = (await db.execute(select(TenantSophiaConnection).where(
        TenantSophiaConnection.tenant_id == auth.tenant_id,
        TenantSophiaConnection.is_enabled.is_(True),
    ))).scalar_one_or_none()
    if connection is None:
        raise HTTPException(status_code=409, detail="Configure e habilite a conexão SophiA antes de sincronizar.")
    if len(body.student_ids) != len(set(body.student_ids)):
        raise HTTPException(status_code=422, detail="A lista de alunos contém IDs duplicados.")
    existing = (await db.execute(select(SophiaSyncJob).where(
        SophiaSyncJob.tenant_id == auth.tenant_id,
        SophiaSyncJob.idempotency_key == body.idempotency_key,
    ))).scalar_one_or_none()
    if existing:
        return {"job_id": existing.id, "status": existing.status, "idempotent_replay": True}
    job = SophiaSyncJob(
        id=str(uuid4()), tenant_id=auth.tenant_id, idempotency_key=body.idempotency_key,
        request={"student_ids": body.student_ids},
    )
    db.add(job)
    await db.flush()
    db.add(SophiaSyncJobEvent(
        tenant_id=auth.tenant_id, job_id=job.id, event_type="queued",
        details={"requested_student_count": len(body.student_ids), "scope": "all_linked" if not body.student_ids else "selected"},
    ))
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Já existe uma sincronização ativa para esta instituição ou a chave idempotente foi reutilizada.") from exc
    return {"job_id": job.id, "status": "queued", "idempotent_replay": False}


@router.get("/jobs")
async def list_sophia_sync_jobs(
    limit: int = 50,
    auth: AuthContext = Depends(require_min_role("coordinator")),
    db: AsyncSession = Depends(get_db),
):
    await _tenant(db, auth.tenant_id)
    rows = (await db.execute(select(SophiaSyncJob).where(
        SophiaSyncJob.tenant_id == auth.tenant_id
    ).order_by(SophiaSyncJob.created_at.desc()).limit(max(1, min(limit, 200))))).scalars().all()
    return {"jobs": [{
        "id": row.id, "status": row.status, "attempts": row.attempts,
        "created_at": row.created_at.isoformat(),
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        "error_code": row.error_code, "error_message": row.error_message,
    } for row in rows]}


@router.get("/jobs/{job_id}")
async def get_sophia_sync_job(
    job_id: str,
    auth: AuthContext = Depends(require_min_role("coordinator")),
    db: AsyncSession = Depends(get_db),
):
    await _tenant(db, auth.tenant_id)
    row = (await db.execute(select(SophiaSyncJob).where(
        SophiaSyncJob.id == job_id, SophiaSyncJob.tenant_id == auth.tenant_id,
    ))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Execução não encontrada.")
    events = (await db.execute(select(SophiaSyncJobEvent).where(
        SophiaSyncJobEvent.job_id == job_id, SophiaSyncJobEvent.tenant_id == auth.tenant_id,
    ).order_by(SophiaSyncJobEvent.created_at))).scalars().all()
    return {
        "id": row.id, "status": row.status, "attempts": row.attempts,
        "created_at": row.created_at.isoformat(),
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        "error_code": row.error_code, "error_message": row.error_message,
        "events": [{"event_type": event.event_type, "details": event.details,
                    "created_at": event.created_at.isoformat()} for event in events],
    }


@router.get("/students/{student_id}/resources")
async def get_sophia_student_resources(
    student_id: str,
    auth: AuthContext = Depends(require_min_role("coordinator")),
    db: AsyncSession = Depends(get_db),
):
    await _tenant(db, auth.tenant_id)
    rows = (await db.execute(select(SophiaStudentResource).where(
        SophiaStudentResource.tenant_id == auth.tenant_id,
        SophiaStudentResource.student_id == student_id,
    ).order_by(SophiaStudentResource.resource))).scalars().all()
    return {"student_id": student_id, "resources": [{
        "resource": row.resource, "payload": row.payload,
        "record_count": row.record_count,
        "source_codigo_interno": row.source_codigo_interno,
        "observed_at": row.observed_at.isoformat(), "updated_at": row.updated_at.isoformat(),
    } for row in rows]}
