"""Wave 13.4 — MIRA Base global lifecycle endpoints."""
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
from app.models.mira_base_lifecycle import MiraBaseLifecycleEvent
from app.models.tenant import ModelArtifact
from app.services.mira_base_lifecycle import (
    MiraBaseLifecycleError,
    activate_base,
    approve_base,
    get_active_base,
    register_base_candidate,
    reject_base,
    rollback_base,
)

router = APIRouter(prefix="/admin/mira-governance", tags=["MIRA Admin - Governance"])


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


class RegisterCandidatePayload(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    version: str = Field(min_length=1, max_length=40)
    run_id: UUID
    metrics: dict | None = None
    feature_columns: list | None = None
    storage_path: str | None = Field(default=None, max_length=500)
    reason: str = Field(min_length=3, max_length=500)

    @field_validator("name", "version", "reason")
    @classmethod
    def normalize(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Campo obrigatório.")
        return normalized


class LifecycleReasonPayload(BaseModel):
    reason: str = Field(min_length=3, max_length=500)

    @field_validator("reason")
    @classmethod
    def normalize(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 3:
            raise ValueError("Justificativa mínima de 3 caracteres.")
        return normalized


async def _audit(
    db: AsyncSession,
    *,
    admin: AdminPrincipal,
    request: Request,
    action: str,
    target_id: str,
    reason: str,
    details: dict | None = None,
) -> None:
    db.add(
        AdminAuditEvent(
            actor_admin_id=admin.id,
            action=action,
            result="success",
            target_type="mira_base_artifact",
            target_id=target_id,
            reason=reason,
            request_id=request.headers.get("x-request-id"),
            metadata_redacted={
                "path": request.url.path,
                "method": request.method,
                **(details or {}),
            },
        )
    )


@router.get("/mira-base/active")
async def get_active_mira_base(
    _admin: AdminPrincipal = Depends(admin_permission("governance:read")),
    db: AsyncSession = Depends(get_db),
):
    state = await get_active_base(db)
    if state is None:
        return {"active": None}
    return {
        "active": {
            "artifact_id": state.artifact_id,
            "name": state.name,
            "version": state.version,
            "lifecycle_status": state.lifecycle_status,
            "is_active": state.is_active,
            "run_id": state.run_id,
        }
    }


@router.get("/mira-base/artifacts")
async def list_base_artifacts(
    limit: int = Query(default=50, ge=1, le=200),
    _admin: AdminPrincipal = Depends(admin_permission("governance:read")),
    db: AsyncSession = Depends(get_db),
):
    rows = (
        await db.execute(
            select(ModelArtifact)
            .where(ModelArtifact.tenant_id.is_(None), ModelArtifact.scope == "base")
            .order_by(ModelArtifact.created_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    return {
        "artifacts": [
            {
                "id": a.id,
                "name": a.name,
                "version": a.version,
                "lifecycle_status": a.lifecycle_status,
                "is_active": a.is_active,
                "run_id": a.run_id,
                "metrics": a.metrics,
                "approved_at": _iso(a.approved_at),
                "activated_at": _iso(a.activated_at),
                "retired_at": _iso(a.retired_at),
                "rollback_of_artifact_id": a.rollback_of_artifact_id,
                "created_at": _iso(a.created_at),
            }
            for a in rows
        ]
    }


@router.get("/mira-base/events")
async def list_base_lifecycle_events(
    limit: int = Query(default=100, ge=1, le=500),
    _admin: AdminPrincipal = Depends(admin_permission("audit:read")),
    db: AsyncSession = Depends(get_db),
):
    rows = (
        await db.execute(
            select(MiraBaseLifecycleEvent)
            .order_by(MiraBaseLifecycleEvent.created_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    return {
        "events": [
            {
                "id": e.id,
                "artifact_id": e.artifact_id,
                "run_id": e.run_id,
                "event_type": e.event_type,
                "from_status": e.from_status,
                "to_status": e.to_status,
                "reason": e.reason,
                "actor_admin_id": e.actor_admin_id,
                "rollback_of_artifact_id": e.rollback_of_artifact_id,
                "metadata": e.metadata_redacted,
                "created_at": _iso(e.created_at),
            }
            for e in rows
        ]
    }


@router.post("/mira-base/candidates", status_code=201)
async def register_candidate_endpoint(
    body: RegisterCandidatePayload,
    request: Request,
    admin: AdminPrincipal = Depends(admin_permission("governance:write")),
    db: AsyncSession = Depends(get_db),
):
    try:
        state = await register_base_candidate(
            db,
            name=body.name,
            version=body.version,
            run_id=str(body.run_id),
            metrics=body.metrics,
            feature_columns=body.feature_columns,
            storage_path=body.storage_path,
            actor_admin_id=admin.id,
            reason=body.reason,
        )
    except MiraBaseLifecycleError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await _audit(
        db, admin=admin, request=request, action="governance.mira_base.candidate_registered",
        target_id=state.artifact_id, reason=body.reason,
        details={"version": state.version, "run_id": state.run_id},
    )
    await db.commit()
    return {
        "artifact_id": state.artifact_id,
        "lifecycle_status": state.lifecycle_status,
        "version": state.version,
        "run_id": state.run_id,
    }


@router.post("/mira-base/artifacts/{artifact_id}/approve", status_code=200)
async def approve_endpoint(
    artifact_id: str,
    body: LifecycleReasonPayload,
    request: Request,
    admin: AdminPrincipal = Depends(admin_permission("governance:write")),
    db: AsyncSession = Depends(get_db),
):
    try:
        state = await approve_base(
            db, artifact_id=artifact_id, actor_admin_id=admin.id, reason=body.reason
        )
    except MiraBaseLifecycleError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await _audit(
        db, admin=admin, request=request, action="governance.mira_base.approved",
        target_id=state.artifact_id, reason=body.reason,
    )
    await db.commit()
    return {"artifact_id": state.artifact_id, "lifecycle_status": state.lifecycle_status}


@router.post("/mira-base/artifacts/{artifact_id}/reject", status_code=200)
async def reject_endpoint(
    artifact_id: str,
    body: LifecycleReasonPayload,
    request: Request,
    admin: AdminPrincipal = Depends(admin_permission("governance:write")),
    db: AsyncSession = Depends(get_db),
):
    try:
        state = await reject_base(
            db, artifact_id=artifact_id, actor_admin_id=admin.id, reason=body.reason
        )
    except MiraBaseLifecycleError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await _audit(
        db, admin=admin, request=request, action="governance.mira_base.rejected",
        target_id=state.artifact_id, reason=body.reason,
    )
    await db.commit()
    return {"artifact_id": state.artifact_id, "lifecycle_status": state.lifecycle_status}


@router.post("/mira-base/artifacts/{artifact_id}/activate", status_code=200)
async def activate_endpoint(
    artifact_id: str,
    body: LifecycleReasonPayload,
    request: Request,
    admin: AdminPrincipal = Depends(admin_permission("governance:write")),
    db: AsyncSession = Depends(get_db),
):
    try:
        state = await activate_base(
            db, artifact_id=artifact_id, actor_admin_id=admin.id, reason=body.reason
        )
    except MiraBaseLifecycleError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await _audit(
        db, admin=admin, request=request, action="governance.mira_base.activated",
        target_id=state.artifact_id, reason=body.reason,
    )
    await db.commit()
    return {
        "artifact_id": state.artifact_id,
        "lifecycle_status": state.lifecycle_status,
        "is_active": state.is_active,
    }


@router.post("/mira-base/artifacts/{artifact_id}/rollback", status_code=200)
async def rollback_endpoint(
    artifact_id: str,
    body: LifecycleReasonPayload,
    request: Request,
    admin: AdminPrincipal = Depends(admin_permission("governance:write")),
    db: AsyncSession = Depends(get_db),
):
    try:
        state = await rollback_base(
            db, target_artifact_id=artifact_id, actor_admin_id=admin.id, reason=body.reason
        )
    except MiraBaseLifecycleError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await _audit(
        db, admin=admin, request=request, action="governance.mira_base.rollback",
        target_id=state.artifact_id, reason=body.reason,
    )
    await db.commit()
    return {
        "artifact_id": state.artifact_id,
        "lifecycle_status": state.lifecycle_status,
        "is_active": state.is_active,
    }
