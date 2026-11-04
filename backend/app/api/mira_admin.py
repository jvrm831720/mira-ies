"""Read-only governance console for modalities, data permissions, runs and model versions."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field, model_validator

from app.api.control_center_auth import admin_permission
from app.db.session import get_db
from app.models.control_center import AdminAuditEvent, AdminPrincipal
from app.models.data_governance import TenantDataUsePolicy
from app.models.institutional_training_authorization import InstitutionalTrainingAuthorization
from app.models.tenant import ModelArtifact, Tenant, TrainingEvent

router = APIRouter(prefix="/admin/mira-governance", tags=["MIRA Admin - Governance"])


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _active(now: datetime, effective_at: datetime, expires_at: datetime | None, revoked_at: datetime | None) -> bool:
    return effective_at <= now and (expires_at is None or expires_at > now) and revoked_at is None


@router.get("/modalities")
async def list_modalities(
    _admin: AdminPrincipal = Depends(admin_permission("governance:read")),
):
    return {
        "modalities": [
            {"id": "institution_only", "label": "Treinamento isolado por instituição",
             "description": "Dados e artefatos permanecem no escopo da instituição; exige autorização institucional vigente."},
            {"id": "shared_training", "label": "Treinamento compartilhado",
             "description": "Eventos só podem compor conjunto compartilhado quando cada instituição possui política aprovada e vigente."},
        ]
    }


@router.get("/authorizations")
async def list_authorizations(
    limit: int = Query(default=100, ge=1, le=500),
    _admin: AdminPrincipal = Depends(admin_permission("governance:read")),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    policies = (await db.execute(
        select(TenantDataUsePolicy, Tenant.name, Tenant.slug)
        .join(Tenant, Tenant.id == TenantDataUsePolicy.tenant_id)
        .order_by(TenantDataUsePolicy.created_at.desc()).limit(limit)
    )).all()
    local = (await db.execute(
        select(InstitutionalTrainingAuthorization, Tenant.name, Tenant.slug)
        .join(Tenant, Tenant.id == InstitutionalTrainingAuthorization.tenant_id)
        .order_by(InstitutionalTrainingAuthorization.created_at.desc()).limit(limit)
    )).all()
    return {
        "shared_data_policies": [{
            "id": p.id, "tenant_id": p.tenant_id, "tenant_name": name, "tenant_slug": slug,
            "mode": p.mode, "contract_reference": p.contract_reference, "contract_version": p.contract_version,
            "effective_at": _iso(p.effective_at), "expires_at": _iso(p.expires_at),
            "revoked_at": _iso(p.revoked_at), "approved_by_admin_id": p.approved_by_admin_id,
            "evidence_reference": p.evidence_reference, "reason": p.reason,
            "is_current": _active(now, p.effective_at, p.expires_at, p.revoked_at),
        } for p, name, slug in policies],
        "institutional_training": [{
            "id": a.id, "tenant_id": a.tenant_id, "tenant_name": name, "tenant_slug": slug,
            "contract_reference": a.contract_reference, "contract_version": a.contract_version,
            "effective_at": _iso(a.effective_at), "expires_at": _iso(a.expires_at),
            "revoked_at": _iso(a.revoked_at), "approved_by_admin_id": a.approved_by_admin_id,
            "evidence_reference": a.evidence_reference, "dataset_eligibility_reference": a.dataset_eligibility_reference,
            "reason": a.reason, "is_current": _active(now, a.effective_at, a.expires_at, a.revoked_at),
        } for a, name, slug in local],
    }


@router.get("/datasets")
async def list_dataset_inventory(
    _admin: AdminPrincipal = Depends(admin_permission("governance:read")),
    db: AsyncSession = Depends(get_db),
):
    tenant_rows = (await db.execute(
        select(Tenant.id, Tenant.name, Tenant.slug, Tenant.is_active)
        .order_by(Tenant.name.asc())
    )).all()
    result = []
    for tenant_id, name, slug, is_active in tenant_rows:
        event_count = await db.scalar(select(func.count()).select_from(TrainingEvent).where(TrainingEvent.tenant_id == tenant_id)) or 0
        labeled_count = await db.scalar(select(func.count()).select_from(TrainingEvent).where(
            TrainingEvent.tenant_id == tenant_id, TrainingEvent.label.is_not(None)
        )) or 0
        result.append({
            "tenant_id": tenant_id, "tenant_name": name, "tenant_slug": slug,
            "institution_active": is_active, "training_events": event_count, "labeled_events": labeled_count,
            "dataset_eligibility": "not_assessed",
            "note": "Contagem operacional; elegibilidade depende da autorização vigente e da política de uso.",
        })
    return {"datasets": result}


@router.get("/runs")
async def list_training_runs(
    limit: int = Query(default=100, ge=1, le=500),
    _admin: AdminPrincipal = Depends(admin_permission("governance:read")),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(
        select(ModelArtifact, Tenant.name, Tenant.slug)
        .outerjoin(Tenant, Tenant.id == ModelArtifact.tenant_id)
        .order_by(ModelArtifact.created_at.desc()).limit(limit)
    )).all()
    return {"runs": [{
        "run_id": a.run_id, "artifact_id": a.id, "tenant_id": a.tenant_id,
        "tenant_name": name or "Global / base", "tenant_slug": slug,
        "name": a.name, "version": a.version, "scope": a.scope,
        "status": a.lifecycle_status, "is_active": a.is_active,
        "created_at": _iso(a.created_at), "trained_at": _iso(a.trained_at),
        "approved_at": _iso(a.approved_at), "activated_at": _iso(a.activated_at),
        "evaluation_report": a.evaluation_report, "metrics": a.metrics,
        "rollback_of_artifact_id": a.rollback_of_artifact_id,
    } for a, name, slug in rows]}


@router.get("/audit")
async def list_governance_audit(
    limit: int = Query(default=100, ge=1, le=500),
    _admin: AdminPrincipal = Depends(admin_permission("audit:read")),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(
        select(AdminAuditEvent, AdminPrincipal.email)
        .outerjoin(AdminPrincipal, AdminPrincipal.id == AdminAuditEvent.actor_admin_id)
        .where(
            (AdminAuditEvent.action.ilike("%model%"))
            | (AdminAuditEvent.action.ilike("%train%"))
            | (AdminAuditEvent.action.ilike("%data%"))
            | (AdminAuditEvent.action.ilike("%authoriz%"))
            | (AdminAuditEvent.action.ilike("%govern%"))
        )
        .order_by(AdminAuditEvent.created_at.desc()).limit(limit)
    )).all()
    return {"events": [{
        "id": e.id, "actor_admin_id": e.actor_admin_id, "actor_email": email,
        "action": e.action, "result": e.result, "target_type": e.target_type,
        "target_id": e.target_id, "reason": e.reason, "request_id": e.request_id,
        "metadata": e.metadata_redacted, "created_at": _iso(e.created_at),
    } for e, email in rows]}


class SharedDataPolicyPayload(BaseModel):
    tenant_id: str = Field(min_length=36, max_length=36)
    mode: Literal["shared_training", "institution_only"]
    contract_reference: str = Field(min_length=1, max_length=160)
    contract_version: str = Field(min_length=1, max_length=80)
    effective_at: datetime
    expires_at: datetime | None = None
    evidence_reference: str = Field(min_length=1, max_length=500)
    reason: str = Field(min_length=3, max_length=500)

    @model_validator(mode="after")
    def validate_dates(self):
        if self.effective_at.tzinfo is None or self.effective_at.utcoffset() is None:
            raise ValueError("effective_at precisa conter fuso horário.")
        if self.expires_at is not None:
            if self.expires_at.tzinfo is None or self.expires_at.utcoffset() is None:
                raise ValueError("expires_at precisa conter fuso horário.")
            if self.expires_at <= self.effective_at:
                raise ValueError("expires_at precisa ser posterior a effective_at.")
        return self


class InstitutionalAuthorizationPayload(BaseModel):
    tenant_id: str = Field(min_length=36, max_length=36)
    contract_reference: str = Field(min_length=1, max_length=160)
    contract_version: str = Field(min_length=1, max_length=80)
    effective_at: datetime
    expires_at: datetime | None = None
    evidence_reference: str = Field(min_length=1, max_length=500)
    dataset_eligibility_reference: str = Field(min_length=1, max_length=500)
    reason: str = Field(min_length=3, max_length=500)

    @model_validator(mode="after")
    def validate_dates(self):
        if self.effective_at.tzinfo is None or self.effective_at.utcoffset() is None:
            raise ValueError("effective_at precisa conter fuso horário.")
        if self.expires_at is not None:
            if self.expires_at.tzinfo is None or self.expires_at.utcoffset() is None:
                raise ValueError("expires_at precisa conter fuso horário.")
            if self.expires_at <= self.effective_at:
                raise ValueError("expires_at precisa ser posterior a effective_at.")
        return self


class GovernanceRevokePayload(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


async def _append_governance_audit(
    db: AsyncSession,
    *,
    admin: AdminPrincipal,
    request: Request,
    action: str,
    target_type: str,
    target_id: str,
    tenant_id: str,
    reason: str,
) -> None:
    db.add(AdminAuditEvent(
        actor_admin_id=admin.id,
        action=action,
        result="success",
        target_type=target_type,
        target_id=target_id,
        reason=reason,
        request_id=request.headers.get("x-request-id"),
        metadata_redacted={"tenant_id": tenant_id, "path": request.url.path, "method": request.method},
    ))


@router.post("/authorizations/shared", status_code=201)
async def create_shared_data_policy(
    body: SharedDataPolicyPayload,
    request: Request,
    admin: AdminPrincipal = Depends(admin_permission("governance:write")),
    db: AsyncSession = Depends(get_db),
):
    tenant = await db.get(Tenant, body.tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Instituição não encontrada.")
    policy = TenantDataUsePolicy(
        id=str(uuid4()),
        tenant_id=tenant.id,
        mode=body.mode,
        contract_reference=body.contract_reference.strip(),
        contract_version=body.contract_version.strip(),
        effective_at=body.effective_at,
        expires_at=body.expires_at,
        approved_by_admin_id=admin.id,
        evidence_reference=body.evidence_reference.strip(),
        reason=body.reason.strip(),
    )
    db.add(policy)
    await db.flush()
    await _append_governance_audit(
        db, admin=admin, request=request, action="governance.shared_policy.created",
        target_type="tenant_data_use_policy", target_id=policy.id,
        tenant_id=tenant.id, reason=body.reason.strip(),
    )
    await db.commit()
    return {"policy_id": policy.id, "tenant_id": tenant.id, "mode": policy.mode, "status": "recorded"}


@router.post("/authorizations/shared/{policy_id}/revoke", status_code=201)
async def revoke_shared_data_policy(
    policy_id: str,
    body: GovernanceRevokePayload,
    request: Request,
    admin: AdminPrincipal = Depends(admin_permission("governance:write")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(TenantDataUsePolicy).where(TenantDataUsePolicy.id == policy_id).with_for_update()
    )
    policy = result.scalar_one_or_none()
    if not policy:
        raise HTTPException(status_code=404, detail="Política não encontrada.")
    latest = await db.execute(
        select(TenantDataUsePolicy)
        .where(TenantDataUsePolicy.tenant_id == policy.tenant_id)
        .order_by(TenantDataUsePolicy.created_at.desc(), TenantDataUsePolicy.effective_at.desc())
        .limit(1)
    )
    current = latest.scalar_one_or_none()
    if current is None or current.id != policy.id or policy.revoked_at is not None:
        raise HTTPException(status_code=409, detail="Somente a política mais recente e não revogada pode ser revogada.")
    now = datetime.now(timezone.utc)
    revocation = TenantDataUsePolicy(
        id=str(uuid4()), tenant_id=policy.tenant_id, mode=policy.mode,
        contract_reference=policy.contract_reference, contract_version=policy.contract_version,
        effective_at=now, expires_at=None, revoked_at=now,
        approved_by_admin_id=admin.id, evidence_reference=policy.evidence_reference,
        reason=body.reason.strip(),
    )
    db.add(revocation)
    await db.flush()
    await _append_governance_audit(
        db, admin=admin, request=request, action="governance.shared_policy.revoked",
        target_type="tenant_data_use_policy", target_id=revocation.id,
        tenant_id=policy.tenant_id, reason=body.reason.strip(),
    )
    await db.commit()
    return {"policy_id": revocation.id, "supersedes_policy_id": policy.id, "status": "revoked"}


@router.post("/authorizations/institutional", status_code=201)
async def create_institutional_training_authorization(
    body: InstitutionalAuthorizationPayload,
    request: Request,
    admin: AdminPrincipal = Depends(admin_permission("governance:write")),
    db: AsyncSession = Depends(get_db),
):
    tenant = await db.get(Tenant, body.tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Instituição não encontrada.")
    authorization = InstitutionalTrainingAuthorization(
        id=str(uuid4()),
        tenant_id=tenant.id,
        contract_reference=body.contract_reference.strip(),
        contract_version=body.contract_version.strip(),
        effective_at=body.effective_at,
        expires_at=body.expires_at,
        approved_by_admin_id=admin.id,
        evidence_reference=body.evidence_reference.strip(),
        dataset_eligibility_reference=body.dataset_eligibility_reference.strip(),
        reason=body.reason.strip(),
    )
    db.add(authorization)
    await db.flush()
    await _append_governance_audit(
        db, admin=admin, request=request, action="governance.institutional_authorization.created",
        target_type="institutional_training_authorization", target_id=authorization.id,
        tenant_id=tenant.id, reason=body.reason.strip(),
    )
    await db.commit()
    return {"authorization_id": authorization.id, "tenant_id": tenant.id, "status": "recorded"}


@router.post("/authorizations/institutional/{authorization_id}/revoke", status_code=201)
async def revoke_institutional_training_authorization(
    authorization_id: str,
    body: GovernanceRevokePayload,
    request: Request,
    admin: AdminPrincipal = Depends(admin_permission("governance:write")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(InstitutionalTrainingAuthorization)
        .where(InstitutionalTrainingAuthorization.id == authorization_id)
        .with_for_update()
    )
    authorization = result.scalar_one_or_none()
    if not authorization:
        raise HTTPException(status_code=404, detail="Autorização institucional não encontrada.")
    latest = await db.execute(
        select(InstitutionalTrainingAuthorization)
        .where(InstitutionalTrainingAuthorization.tenant_id == authorization.tenant_id)
        .order_by(
            InstitutionalTrainingAuthorization.created_at.desc(),
            InstitutionalTrainingAuthorization.effective_at.desc(),
        )
        .limit(1)
    )
    current = latest.scalar_one_or_none()
    if current is None or current.id != authorization.id or authorization.revoked_at is not None:
        raise HTTPException(status_code=409, detail="Somente a autorização mais recente e não revogada pode ser revogada.")
    now = datetime.now(timezone.utc)
    revocation = InstitutionalTrainingAuthorization(
        id=str(uuid4()), tenant_id=authorization.tenant_id,
        contract_reference=authorization.contract_reference,
        contract_version=authorization.contract_version,
        effective_at=now, expires_at=None, revoked_at=now,
        approved_by_admin_id=admin.id, evidence_reference=authorization.evidence_reference,
        dataset_eligibility_reference=authorization.dataset_eligibility_reference,
        reason=body.reason.strip(),
    )
    db.add(revocation)
    await db.flush()
    await _append_governance_audit(
        db, admin=admin, request=request, action="governance.institutional_authorization.revoked",
        target_type="institutional_training_authorization", target_id=revocation.id,
        tenant_id=authorization.tenant_id, reason=body.reason.strip(),
    )
    await db.commit()
    return {"authorization_id": revocation.id, "supersedes_authorization_id": authorization.id, "status": "revoked"}
