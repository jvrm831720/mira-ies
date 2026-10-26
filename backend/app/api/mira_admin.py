"""Read-only governance console for modalities, data permissions, runs and model versions."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

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
