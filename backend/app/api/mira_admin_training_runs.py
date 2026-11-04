"""Wave 13.3 — internal endpoints for training runs and dataset snapshots."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.control_center_auth import admin_permission
from app.db.session import get_db
from app.models.control_center import AdminAuditEvent, AdminPrincipal
from app.models.training_run import TrainingDatasetSnapshot, TrainingRun
from app.services.training_run_service import (
    TrainingRunBlockedError,
    create_shared_base_training_run,
    mark_run_status,
)

router = APIRouter(prefix="/admin/mira-governance", tags=["MIRA Admin - Governance"])


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


class CreateSharedRunPayload(BaseModel):
    contributing_tenant_ids: list[UUID] = Field(min_length=1)
    run_key: str | None = Field(default=None, max_length=80)


class UpdateRunStatusPayload(BaseModel):
    status: str = Field(pattern="^(queued|running|succeeded|failed|cancelled)$")
    metrics: dict | None = None
    error_message: str | None = Field(default=None, max_length=2000)
    artifact_id: UUID | None = None

    @field_validator("error_message")
    @classmethod
    def normalize_error(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


async def _append_audit(db, *, admin, request, action, target_id, reason, details=None):
    db.add(AdminAuditEvent(
        actor_admin_id=admin.id, action=action, result="success",
        target_type="training_run", target_id=target_id, reason=reason,
        request_id=request.headers.get("x-request-id"),
        metadata_redacted={"path": request.url.path, "method": request.method, **(details or {})},
    ))


@router.get("/training-runs")
async def list_training_runs(
    limit: int = Query(default=100, ge=1, le=500),
    scope: str | None = Query(default=None, pattern="^(shared_base|institutional)$"),
    status: str | None = Query(default=None, pattern="^(queued|running|succeeded|failed|cancelled)$"),
    _admin: AdminPrincipal = Depends(admin_permission("governance:read")),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(TrainingRun).order_by(TrainingRun.created_at.desc()).limit(limit)
    if scope:
        stmt = stmt.where(TrainingRun.scope == scope)
    if status:
        stmt = stmt.where(TrainingRun.status == status)
    rows = (await db.execute(stmt)).scalars().all()
    return {"runs": [{
        "id": r.id, "run_key": r.run_key, "scope": r.scope, "tenant_id": r.tenant_id,
        "snapshot_id": r.snapshot_id, "dataset_hash": r.dataset_hash, "status": r.status,
        "triggered_by_admin_id": r.triggered_by_admin_id, "artifact_id": r.artifact_id,
        "metrics": r.metrics, "error_message": r.error_message,
        "started_at": _iso(r.started_at), "finished_at": _iso(r.finished_at), "created_at": _iso(r.created_at),
    } for r in rows]}


@router.get("/dataset-snapshots")
async def list_dataset_snapshots(
    limit: int = Query(default=50, ge=1, le=200),
    _admin: AdminPrincipal = Depends(admin_permission("governance:read")),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(select(TrainingDatasetSnapshot).order_by(TrainingDatasetSnapshot.built_at.desc()).limit(limit))).scalars().all()
    return {"snapshots": [{
        "id": s.id, "scope": s.scope, "dataset_hash": s.dataset_hash,
        "contribution_hashes": s.contribution_hashes, "tenant_ids": s.tenant_ids,
        "row_count": s.row_count, "anonymization_rules_version": s.anonymization_rules_version,
        "feature_schema_version": s.feature_schema_version, "built_by_admin_id": s.built_by_admin_id,
        "built_at": _iso(s.built_at), "created_at": _iso(s.created_at),
    } for s in rows]}


@router.post("/training-runs/shared", status_code=201)
async def create_shared_training_run_endpoint(
    body: CreateSharedRunPayload, request: Request,
    admin: AdminPrincipal = Depends(admin_permission("governance:write")),
    db: AsyncSession = Depends(get_db),
):
    try:
        record = await create_shared_base_training_run(
            db, contributing_tenant_ids=[str(t) for t in body.contributing_tenant_ids],
            triggered_by_admin_id=admin.id, run_key=body.run_key,
        )
    except TrainingRunBlockedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    await _append_audit(db, admin=admin, request=request, action="governance.training_run.created",
                         target_id=record.run_id, reason="Shared-base training run queued under eligible contributions.",
                         details={"run_key": record.run_key, "snapshot_id": record.snapshot_id,
                                  "dataset_hash": record.dataset_hash, "tenant_ids": record.tenant_ids, "row_count": record.row_count})
    await db.commit()
    return {"run_id": record.run_id, "run_key": record.run_key, "snapshot_id": record.snapshot_id,
            "dataset_hash": record.dataset_hash, "status": record.status, "scope": record.scope,
            "tenant_ids": record.tenant_ids, "row_count": record.row_count}


@router.post("/training-runs/{run_id}/status", status_code=200)
async def update_training_run_status(
    run_id: str, body: UpdateRunStatusPayload, request: Request,
    admin: AdminPrincipal = Depends(admin_permission("governance:write")),
    db: AsyncSession = Depends(get_db),
):
    try:
        run = await mark_run_status(
            db, run_id=run_id, status=body.status, metrics=body.metrics,
            error_message=body.error_message,
            artifact_id=str(body.artifact_id) if body.artifact_id else None,
        )
    except TrainingRunBlockedError as exp:
        raise HTTPException(status_code=409, detail=str(exp)) from exp
    await _append_audit(db, admin=admin, request=request, action="governance.training_run.status_updated",
                         target_id=run.id, reason=f"Status set to {body.status}",
                         details={"status": body.status, "artifact_id": body.artifact_id and str(body.artifact_id)})
    await db.commit()
    return {"run_id": run.id, "status": run.status, "started_at": _iso(run.started_at),
            "finished_at": _iso(run.finished_at), "metrics": run.metrics, "artifact_id": run.artifact_id}
