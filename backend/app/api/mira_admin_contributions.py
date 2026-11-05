"""Wave 13.2 — internal endpoints for eligible contribution assessment and revocation."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.control_center_auth import admin_permission
from app.db.session import get_db
from app.models.control_center import AdminAuditEvent, AdminPrincipal
from app.models.eligible_contribution import EligibleContribution
from app.models.tenant import Tenant
from app.services.contribution_eligibility import (
    ContributionBlockedError,
    assess_contribution,
    revoke_contribution,
)

router = APIRouter(prefix="/admin/mira-governance", tags=["MIRA Admin - Governance"])


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


class AssessContributionPayload(BaseModel):
    tenant_id: UUID
    contribution_key: str = Field(min_length=1, max_length=128)
    source_dataset_ref: str = Field(min_length=1, max_length=500)
    source_rows: list[dict[str, Any]] = Field(min_length=1)
    approval_reason: str = Field(min_length=3, max_length=500)

    @field_validator("contribution_key", "source_dataset_ref", "approval_reason")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("O campo não pode ficar vazio.")
        return normalized


class RevokeContributionPayload(BaseModel):
    reason: str = Field(min_length=3, max_length=500)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 3:
            raise ValueError("A justificativa precisa ter ao menos 3 caracteres.")
        return normalized


async def _append_audit(
    db: AsyncSession,
    *,
    admin: AdminPrincipal,
    request: Request,
    action: str,
    target_id: str,
    tenant_id: str,
    reason: str,
    details: dict | None = None,
) -> None:
    db.add(
        AdminAuditEvent(
            actor_admin_id=admin.id,
            action=action,
            result="success",
            target_type="eligible_contribution",
            target_id=target_id,
            reason=reason,
            request_id=request.headers.get("x-request-id"),
            metadata_redacted={
                "tenant_id": tenant_id,
                "path": request.url.path,
                "method": request.method,
                **(details or {}),
            },
        )
    )


@router.get("/contributions")
async def list_contributions(
    limit: int = Query(default=100, ge=1, le=500),
    tenant_id: UUID | None = None,
    status: str | None = Query(default=None, pattern="^(eligible|rejected|revoked)$"),
    _admin: AdminPrincipal = Depends(admin_permission("governance:read")),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(EligibleContribution, Tenant.name, Tenant.slug)
        .join(Tenant, Tenant.id == EligibleContribution.tenant_id)
        .order_by(EligibleContribution.created_at.desc())
        .limit(limit)
    )
    if tenant_id is not None:
        stmt = stmt.where(EligibleContribution.tenant_id == str(tenant_id))
    if status is not None:
        stmt = stmt.where(EligibleContribution.eligibility_status == status)
    rows = (await db.execute(stmt)).all()
    return {
        "contributions": [
            {
                "id": c.id,
                "tenant_id": c.tenant_id,
                "tenant_name": name,
                "tenant_slug": slug,
                "contribution_key": c.contribution_key,
                "source_dataset_ref": c.source_dataset_ref,
                "policy_id": c.policy_id,
                "policy_contract_version": c.policy_contract_version,
                "modality": c.modality,
                "eligibility_status": c.eligibility_status,
                "rejection_reason": c.rejection_reason,
                "approval_reason": c.approval_reason,
                "sanitized_content_hash": c.sanitized_content_hash,
                "anonymization_rules_version": c.anonymization_rules_version,
                "feature_schema_version": c.feature_schema_version,
                "row_count": c.row_count,
                "assessed_at": _iso(c.assessed_at),
                "assessed_by_admin_id": c.assessed_by_admin_id,
                "revoked_at": _iso(c.revoked_at),
                "created_at": _iso(c.created_at),
            }
            for c, name, slug in rows
        ]
    }


@router.post("/contributions/assess", status_code=201)
async def assess_contribution_endpoint(
    body: AssessContributionPayload,
    request: Request,
    admin: AdminPrincipal = Depends(admin_permission("governance:write")),
    db: AsyncSession = Depends(get_db),
):
    tenant = await db.get(Tenant, str(body.tenant_id))
    if not tenant:
        raise HTTPException(status_code=404, detail="Instituição não encontrada.")
    try:
        assessment = await assess_contribution(
            db,
            tenant_id=str(body.tenant_id),
            contribution_key=body.contribution_key,
            source_dataset_ref=body.source_dataset_ref,
            source_rows=body.source_rows,
            assessed_by_admin_id=admin.id,
            approval_reason=body.approval_reason,
        )
    except ContributionBlockedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    await _append_audit(
        db,
        admin=admin,
        request=request,
        action="governance.contribution.assessed",
        target_id=assessment.contribution_id,
        tenant_id=assessment.tenant_id,
        reason=assessment.reason,
        details={
            "status": assessment.status,
            "modality": assessment.modality,
            "row_count": assessment.row_count,
            "sanitized_content_hash": assessment.sanitized_content_hash,
        },
    )
    await db.commit()
    return {
        "contribution_id": assessment.contribution_id,
        "tenant_id": assessment.tenant_id,
        "status": assessment.status,
        "modality": assessment.modality,
        "sanitized_content_hash": assessment.sanitized_content_hash,
        "row_count": assessment.row_count,
        "reason": assessment.reason,
        "policy_id": assessment.policy_id,
    }


@router.post("/contributions/{contribution_id}/revoke", status_code=201)
async def revoke_contribution_endpoint(
    contribution_id: str,
    body: RevokeContributionPayload,
    request: Request,
    admin: AdminPrincipal = Depends(admin_permission("governance:write")),
    db: AsyncSession = Depends(get_db),
):
    try:
        assessment = await revoke_contribution(
            db,
            contribution_id=contribution_id,
            reason=body.reason,
            assessed_by_admin_id=admin.id,
        )
    except ContributionBlockedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    await _append_audit(
        db,
        admin=admin,
        request=request,
        action="governance.contribution.revoked",
        target_id=assessment.contribution_id,
        tenant_id=assessment.tenant_id,
        reason=assessment.reason,
        details={
            "status": assessment.status,
            "supersedes_hint": contribution_id,
            "sanitized_content_hash": assessment.sanitized_content_hash,
        },
    )
    await db.commit()
    return {
        "contribution_id": assessment.contribution_id,
        "supersedes_contribution_id": contribution_id,
        "status": assessment.status,
        "reason": assessment.reason,
    }
