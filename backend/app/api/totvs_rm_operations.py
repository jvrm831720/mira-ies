"""Operational API for tenant-scoped TOTVS RM synchronization jobs."""
from __future__ import annotations

import re
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from app.core.auth import AuthContext, require_min_role
from app.db.session import AsyncSessionLocal
from app.services.connectors.totvs_rm_sync_orchestrator import (
    RMJobConflict,
    RMJobNotFound,
    RMPostgresSyncQueue,
)

router = APIRouter(prefix="/integrations/totvs-rm", tags=["Integração TOTVS RM"])
queue = RMPostgresSyncQueue(AsyncSessionLocal)

JOB_STATUSES = {"queued", "running", "retry_wait", "cancel_requested", "publishing", "cancelled", "succeeded", "failed"}


class CreateRMSyncJobBody(BaseModel):
    coligada_id: str = Field(min_length=1, max_length=80)
    source_name: str = Field(min_length=1, max_length=120)
    entity_name: str = Field(min_length=1, max_length=120)
    schema_version: str = Field(default="v1", min_length=1, max_length=40)
    page_size: int = Field(default=500, ge=1, le=1000)
    max_attempts: int = Field(default=5, ge=1, le=12)

    @field_validator("coligada_id", "source_name", "entity_name", "schema_version")
    @classmethod
    def validate_identifier(cls, value: str) -> str:
        value = value.strip()
        if not value or not re.fullmatch(r"[A-Za-z0-9_.:-]+", value):
            raise ValueError("Use somente letras, números, ponto, sublinhado, dois-pontos e hífen.")
        return value


def _conflict(exc: RMJobConflict) -> HTTPException:
    return HTTPException(status_code=409, detail=str(exc))


@router.get("/scopes")
async def list_rm_sync_scopes(
    auth: AuthContext = Depends(require_min_role("coordinator")),
):
    return {"scopes": await queue.scopes(tenant_id=auth.tenant_id)}


@router.post("/sync", status_code=202)
async def enqueue_rm_sync(
    body: CreateRMSyncJobBody,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=160),
    auth: AuthContext = Depends(require_min_role("coordinator")),
):
    try:
        scope_id = await queue.ensure_scope(
            tenant_id=auth.tenant_id,
            coligada_id=body.coligada_id,
            source_name=body.source_name,
            entity_name=body.entity_name,
            schema_version=body.schema_version,
        )
        job_id = await queue.enqueue(
            tenant_id=auth.tenant_id,
            scope_id=scope_id,
            idempotency_key=idempotency_key,
            request={"mode": "full_snapshot", "page_size": body.page_size},
            max_attempts=body.max_attempts,
            actor_user_id=auth.user_id,
            actor_type="user" if auth.user_id else "api_key",
        )
    except RMJobConflict as exc:
        raise _conflict(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    job = await queue.get_job(tenant_id=auth.tenant_id, job_id=str(job_id))
    return {"job_id": job_id, "status": job["status"] if job else "queued", "scope_id": scope_id}


@router.get("/jobs")
async def list_rm_sync_jobs(
    status: str | None = Query(default=None),
    coligada_id: str | None = Query(default=None, min_length=1, max_length=80),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=100000),
    auth: AuthContext = Depends(require_min_role("coordinator")),
):
    if status and status not in JOB_STATUSES:
        raise HTTPException(status_code=422, detail="Status de sincronização inválido.")
    return await queue.list_jobs(
        tenant_id=auth.tenant_id, status=status, coligada_id=coligada_id,
        limit=limit, offset=offset,
    )


@router.get("/jobs/{job_id}")
async def get_rm_sync_job(
    job_id: UUID,
    auth: AuthContext = Depends(require_min_role("coordinator")),
):
    job = await queue.get_job(tenant_id=auth.tenant_id, job_id=str(job_id))
    if not job:
        raise HTTPException(status_code=404, detail="Sincronização não encontrada.")
    return {**job, "events": await queue.events(tenant_id=auth.tenant_id, job_id=str(job_id))}


@router.post("/jobs/{job_id}/cancel")
async def cancel_rm_sync_job(
    job_id: UUID,
    auth: AuthContext = Depends(require_min_role("coordinator")),
):
    try:
        status = await queue.request_cancel(
            tenant_id=auth.tenant_id, job_id=str(job_id), actor_user_id=auth.user_id,
            actor_type="user" if auth.user_id else "api_key",
        )
    except RMJobNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RMJobConflict as exc:
        raise _conflict(exc) from exc
    return {"job_id": str(job_id), "status": status}


@router.post("/jobs/{job_id}/retry", status_code=202)
async def retry_rm_sync_job(
    job_id: UUID,
    auth: AuthContext = Depends(require_min_role("coordinator")),
):
    try:
        return await queue.retry_failed(
            tenant_id=auth.tenant_id, job_id=str(job_id), actor_user_id=auth.user_id,
            actor_type="user" if auth.user_id else "api_key",
        )
    except RMJobNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RMJobConflict as exc:
        raise _conflict(exc) from exc


@router.get("/metrics")
async def get_rm_sync_metrics(
    auth: AuthContext = Depends(require_min_role("coordinator")),
):
    return await queue.metrics(tenant_id=auth.tenant_id)
