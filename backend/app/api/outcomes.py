"""Outcomes e learning loop — protegido por X-API-Key."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional
import hmac
import secrets
from fastapi import APIRouter, Depends, HTTPException, Query, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from pydantic import BaseModel, Field

from app.db.session import get_db
from app.models.tenant import Tenant, TrainingEvent, ModelArtifact
from app.models.intervention import InterventionLog
from app.ml.targets import (
    EXCLUDED_OUTCOMES, SUPPORTED_OUTCOMES, TARGET_DEFINITION_VERSION,
    derive_target_label, normalize_utc_timestamp,
)
from app.services.tenant import get_tenant_learning_stats, ensure_base_model_registered
from app.ml.tenant_train import train_tenant_model, invalidate_tenant_cache
from app.core.auth import AuthContext, get_current_tenant, require_tenant_match
from app.core.security import generate_api_key, hash_api_key
from app.core.config import get_settings

router = APIRouter()


class OutcomeItem(BaseModel):
    matricula: str
    outcome: str
    observed_at: Optional[datetime] = None
    notes: Optional[str] = None
    student_id: Optional[str] = None
    training_event_id: Optional[str] = None


class OutcomeBatchRequest(BaseModel):
    tenant_slug: str = "default"
    outcomes: list[OutcomeItem] = Field(..., min_length=1, max_length=2000)


class TenantCreateRequest(BaseModel):
    slug: str = Field(..., min_length=2, max_length=80, pattern=r"^[a-z0-9][a-z0-9-]*$")
    name: str = Field(..., min_length=1, max_length=255)
    segment: Optional[str] = Field(default=None, max_length=80)


@router.post("/tenants", status_code=201)
async def create_tenant(
    body: TenantCreateRequest,
    db: AsyncSession = Depends(get_db),
    x_admin_secret: str | None = Header(default=None, alias="X-Admin-Secret"),
):
    settings = get_settings()
    if settings.app_env != "development":
        if not x_admin_secret or not hmac.compare_digest(x_admin_secret, settings.secret_key):
            raise HTTPException(status_code=403, detail="X-Admin-Secret invalido")
    existing = await db.execute(select(Tenant).where(Tenant.slug == body.slug))
    t = existing.scalar_one_or_none()
    if t:
        return {"id": t.id, "slug": t.slug, "name": t.name, "message": "Tenant ja existia (API key nao e reexibida)", "api_key": None}
    raw_key = generate_api_key()
    webhook_secret = secrets.token_urlsafe(24)
    t = Tenant(slug=body.slug, name=body.name, segment=body.segment, is_active=True,
               api_key_hash=hash_api_key(raw_key), webhook_secret=webhook_secret)
    db.add(t)
    await ensure_base_model_registered(db)
    await db.commit()
    await db.refresh(t)
    return {"id": t.id, "slug": t.slug, "name": t.name,
            "message": "Tenant criado. Guarde a api_key — nao sera mostrada de novo.",
            "api_key": raw_key, "webhook_secret": webhook_secret}


@router.get("/tenants")
async def list_tenants(auth: AuthContext = Depends(get_current_tenant), db: AsyncSession = Depends(get_db)):
    t = auth.tenant
    return {"count": 1, "tenants": [{"id": t.id, "slug": t.slug, "name": t.name, "segment": t.segment,
        "labeled_events": t.labeled_events_count, "positive_labels": t.positive_labels_count,
        "tenant_model_ready": t.tenant_model_ready}]}


@router.get("/tenants/{slug}/learning")
async def tenant_learning_status(slug: str, auth: AuthContext = Depends(get_current_tenant), db: AsyncSession = Depends(get_db)):
    await require_tenant_match(auth, slug)
    return await get_tenant_learning_stats(db, auth.tenant_id)


@router.post("/outcomes", status_code=201)
async def register_outcomes(body: OutcomeBatchRequest, auth: AuthContext = Depends(get_current_tenant), db: AsyncSession = Depends(get_db)):
    await require_tenant_match(auth, body.tenant_slug)
    tenant = auth.tenant
    now = datetime.now(timezone.utc)
    updated = created = labeled = 0
    attributed_interventions = 0
    errors, deferred, excluded = [], [], []
    for item in body.outcomes:
        outcome_key = item.outcome.strip().lower()
        if outcome_key not in SUPPORTED_OUTCOMES:
            errors.append({"matricula": item.matricula, "error": f"outcome invalido: {item.outcome}"})
            continue
        if item.observed_at and normalize_utc_timestamp(item.observed_at) > now:
            errors.append({"matricula": item.matricula, "error": "observed_at não pode estar no futuro"})
            continue
        event = None
        if item.training_event_id:
            r = await db.execute(select(TrainingEvent).where(TrainingEvent.id == item.training_event_id, TrainingEvent.tenant_id == tenant.id))
            event = r.scalar_one_or_none()
            if not event:
                errors.append({"matricula": item.matricula, "error": "training_event_id não encontrado para este tenant"})
                continue
            if event.matricula != item.matricula:
                errors.append({"matricula": item.matricula, "error": "training_event_id não corresponde à matrícula informada"})
                continue
        else:
            r = await db.execute(select(TrainingEvent).where(TrainingEvent.tenant_id == tenant.id, TrainingEvent.matricula == item.matricula).order_by(TrainingEvent.scored_at.desc()).limit(1))
            event = r.scalar_one_or_none()
        if not event:
            errors.append({"matricula": item.matricula, "error": "snapshot de pontuação não encontrado; pontue o aluno antes de registrar o desfecho"})
            continue
        try:
            label, label_status = derive_target_label(outcome_key, event.scored_at, item.observed_at)
        except ValueError as exc:
            errors.append({"matricula": item.matricula, "error": str(exc)})
            continue

        event.label = label
        event.target_definition = TARGET_DEFINITION_VERSION if label is not None else None
        event.outcome = outcome_key
        event.outcome_at = item.observed_at
        event.labeled_at = now
        event.outcome_notes = item.notes
        updated += 1

        # Link imported academic outcomes to real messages sent within the previous 90 days.
        # This is observational attribution, not proof the message caused the outcome.
        final_status = {
            "ativo": "stayed", "concluiu": "stayed", "formou": "stayed",
            "evadiu": "dropped", "trancou": "dropped", "transferiu": "transferred",
        }.get(outcome_key)
        if item.observed_at is not None and final_status:
            observed_at = normalize_utc_timestamp(item.observed_at)
            attributed = await db.execute(
                update(InterventionLog)
                .where(
                    InterventionLog.tenant_id == tenant.id,
                    InterventionLog.matricula == item.matricula,
                    InterventionLog.status == "sent",
                    InterventionLog.outcome.is_(None),
                    InterventionLog.created_at >= observed_at - timedelta(days=90),
                    InterventionLog.created_at <= observed_at,
                )
                .values(
                    outcome=final_status,
                    outcome_at=observed_at,
                    outcome_source="import",
                    outcome_note=f"Status acadêmico importado: {outcome_key}"[:240],
                )
            )
            attributed_interventions += max(0, attributed.rowcount or 0)

        if label is not None:
            labeled += 1
        elif outcome_key in EXCLUDED_OUTCOMES:
            excluded.append({"matricula": item.matricula, "outcome": outcome_key, "reason": label_status})
        else:
            deferred.append({"matricula": item.matricula, "outcome": outcome_key, "reason": label_status})
    await db.flush()
    stats = await get_tenant_learning_stats(db, tenant.id)
    await db.commit()
    return {
        "message": f"{updated} outcomes registrados; {labeled} rotulos elegiveis para o alvo de 90 dias",
        "updated": updated, "created": created, "labeled": labeled,
        "attributed_interventions": attributed_interventions,
        "deferred": deferred, "excluded_from_training": excluded,
        "errors": errors, "target_definition": TARGET_DEFINITION_VERSION, "learning": stats,
    }


@router.get("/training-events")
async def list_training_events(
    tenant_slug: str = Query("default"), labeled_only: bool = Query(False),
    limit: int = Query(50, ge=1, le=500),
    auth: AuthContext = Depends(get_current_tenant), db: AsyncSession = Depends(get_db),
):
    await require_tenant_match(auth, tenant_slug)
    q = select(TrainingEvent).where(TrainingEvent.tenant_id == auth.tenant_id)
    if labeled_only:
        q = q.where(TrainingEvent.label.is_not(None), TrainingEvent.target_definition == TARGET_DEFINITION_VERSION)
    q = q.order_by(TrainingEvent.scored_at.desc()).limit(limit)
    events = (await db.execute(q)).scalars().all()
    return {"tenant": auth.tenant_slug, "count": len(events), "events": [{
        "id": e.id, "matricula": e.matricula, "scored_at": e.scored_at, "adjusted_score": e.adjusted_score,
        "risk_level": e.risk_level,
        "label": e.label if e.target_definition == TARGET_DEFINITION_VERSION else None,
        "historical_label": e.label if e.target_definition != TARGET_DEFINITION_VERSION else None,
        "target_definition": e.target_definition, "outcome": e.outcome, "outcome_at": e.outcome_at,
        "labeled_at": e.labeled_at, "model_scope": e.model_scope,
    } for e in events]}


@router.post("/tenants/{slug}/train")
async def train_tenant_endpoint(
    slug: str, force: bool = Query(False),
    auth: AuthContext = Depends(get_current_tenant), db: AsyncSession = Depends(get_db),
):
    await require_tenant_match(auth, slug)
    try:
        return await train_tenant_model(db, tenant_slug=auth.tenant_slug, force=force)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro no treino: {str(e)}")


@router.get("/tenants/{slug}/models")
async def list_tenant_models(slug: str, auth: AuthContext = Depends(get_current_tenant), db: AsyncSession = Depends(get_db)):
    await require_tenant_match(auth, slug)
    result = await db.execute(select(ModelArtifact).where(
        (ModelArtifact.tenant_id == auth.tenant_id) | (ModelArtifact.scope == "base")
    ).order_by(ModelArtifact.created_at.desc()))
    arts = result.scalars().all()
    active_tenant_artifact = None
    if auth.tenant.active_model_id:
        active_result = await db.execute(select(ModelArtifact).where(
            ModelArtifact.id == auth.tenant.active_model_id,
            ModelArtifact.tenant_id == auth.tenant_id,
            ModelArtifact.scope == "tenant",
            ModelArtifact.is_active == True,  # noqa: E712
        ))
        candidate = active_result.scalar_one_or_none()
        if candidate and (candidate.metrics or {}).get("target_definition") == TARGET_DEFINITION_VERSION:
            active_tenant_artifact = candidate
    using_tenant_model = active_tenant_artifact is not None
    return {
        "tenant": slug,
        "active_model": "tenant" if using_tenant_model else "base",
        "active_model_id": active_tenant_artifact.id if active_tenant_artifact else None,
        "models": [{
        "id": a.id, "name": a.name, "version": a.version, "scope": a.scope,
        "is_active": a.is_active, "lifecycle_status": a.lifecycle_status,
        "run_id": a.run_id, "evaluation_report": a.evaluation_report,
        "approved_at": a.approved_at, "activated_at": a.activated_at,
        "rollback_of_artifact_id": a.rollback_of_artifact_id,
        "metrics": a.metrics, "trained_at": a.trained_at,
        "is_used_for_scoring": (
            a.id == active_tenant_artifact.id if active_tenant_artifact
            else a.scope == "base" and a.is_active
        ),
    } for a in arts]}


class ModelLifecycleAction(BaseModel):
    reason: str = Field(..., min_length=8, max_length=500)


def _require_model_approver(auth: AuthContext) -> None:
    # API keys identify a tenant, not a human approver; approvals require a real admin session.
    if auth.role != "admin" or not auth.user_id:
        raise HTTPException(status_code=403, detail="Aprovação de modelo exige sessão de usuário admin identificada.")


@router.post("/tenants/{slug}/models/{artifact_id}/approve")
async def approve_tenant_model(
    slug: str, artifact_id: str, body: ModelLifecycleAction,
    auth: AuthContext = Depends(get_current_tenant), db: AsyncSession = Depends(get_db),
):
    await require_tenant_match(auth, slug)
    _require_model_approver(auth)
    result = await db.execute(select(ModelArtifact).where(
        ModelArtifact.id == artifact_id, ModelArtifact.tenant_id == auth.tenant_id,
        ModelArtifact.scope == "tenant",
    ).with_for_update())
    artifact = result.scalar_one_or_none()
    if not artifact:
        raise HTTPException(status_code=404, detail="Candidato não encontrado para esta instituição.")
    if artifact.lifecycle_status != "candidate" or artifact.is_active:
        raise HTTPException(status_code=409, detail="Somente candidatos não ativos podem ser aprovados.")
    if (artifact.metrics or {}).get("target_definition") != TARGET_DEFINITION_VERSION:
        raise HTTPException(status_code=409, detail="Relatório usa definição de alvo incompatível.")
    artifact.lifecycle_status = "approved"
    artifact.approved_by_user_id = auth.user_id
    artifact.approved_at = datetime.now(timezone.utc)
    artifact.activation_reason = body.reason.strip()
    artifact.evaluation_report = artifact.evaluation_report or artifact.metrics
    await db.commit()
    return {"status": "approved", "artifact_id": artifact.id, "approved_at": artifact.approved_at}


@router.post("/tenants/{slug}/models/{artifact_id}/activate")
async def activate_tenant_model(
    slug: str, artifact_id: str, body: ModelLifecycleAction,
    auth: AuthContext = Depends(get_current_tenant), db: AsyncSession = Depends(get_db),
):
    await require_tenant_match(auth, slug)
    _require_model_approver(auth)
    result = await db.execute(select(ModelArtifact).where(
        ModelArtifact.id == artifact_id, ModelArtifact.tenant_id == auth.tenant_id,
        ModelArtifact.scope == "tenant",
    ).with_for_update())
    artifact = result.scalar_one_or_none()
    if not artifact:
        raise HTTPException(status_code=404, detail="Artefato não encontrado.")
    if artifact.lifecycle_status != "approved" or not artifact.approved_by_user_id:
        raise HTTPException(status_code=409, detail="Modelo precisa de aprovação explícita antes da ativação.")
    if (artifact.metrics or {}).get("target_definition") != TARGET_DEFINITION_VERSION:
        raise HTTPException(status_code=409, detail="Artefato usa definição de alvo antiga; treine novamente.")
    previous_result = await db.execute(select(ModelArtifact).where(
        ModelArtifact.tenant_id == auth.tenant_id, ModelArtifact.scope == "tenant",
        ModelArtifact.is_active.is_(True),
    ).with_for_update())
    previous = previous_result.scalars().all()
    now = datetime.now(timezone.utc)
    for old in previous:
        old.is_active = False
        old.lifecycle_status = "retired"
        old.retired_at = now
    artifact.is_active = True
    artifact.lifecycle_status = "active"
    artifact.activated_at = now
    artifact.activation_reason = body.reason.strip()
    auth.tenant.active_model_id = artifact.id
    await db.commit()
    invalidate_tenant_cache(slug)
    return {"status": "active", "artifact_id": artifact.id, "version": artifact.version, "activated_at": now}


@router.post("/tenants/{slug}/models/{artifact_id}/rollback")
async def rollback_tenant_model(
    slug: str, artifact_id: str, body: ModelLifecycleAction,
    auth: AuthContext = Depends(get_current_tenant), db: AsyncSession = Depends(get_db),
):
    await require_tenant_match(auth, slug)
    _require_model_approver(auth)
    result = await db.execute(select(ModelArtifact).where(
        ModelArtifact.id == artifact_id, ModelArtifact.tenant_id == auth.tenant_id,
        ModelArtifact.scope == "tenant",
    ).with_for_update())
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="Versão anterior não encontrada.")
    if target.lifecycle_status != "retired" or not target.approved_by_user_id:
        raise HTTPException(status_code=409, detail="Rollback exige versão anterior aprovada e aposentada.")
    previous_result = await db.execute(select(ModelArtifact).where(
        ModelArtifact.tenant_id == auth.tenant_id, ModelArtifact.scope == "tenant",
        ModelArtifact.is_active.is_(True),
    ).with_for_update())
    previous = previous_result.scalars().all()
    now = datetime.now(timezone.utc)
    previous_id = previous[0].id if previous else None
    for old in previous:
        old.is_active = False
        old.lifecycle_status = "retired"
        old.retired_at = now
    target.is_active = True
    target.lifecycle_status = "active"
    target.activated_at = now
    target.rollback_of_artifact_id = previous_id
    target.activation_reason = f"ROLLBACK: {body.reason.strip()}"
    auth.tenant.active_model_id = target.id
    await db.commit()
    invalidate_tenant_cache(slug)
    return {"status": "rolled_back", "artifact_id": target.id, "version": target.version,
            "rolled_back_from_artifact_id": previous_id, "reason": body.reason.strip()}


@router.post("/tenants/{slug}/models/deactivate")
async def deactivate_tenant_model(slug: str, auth: AuthContext = Depends(get_current_tenant), db: AsyncSession = Depends(get_db)):
    await require_tenant_match(auth, slug)
    prev = await db.execute(select(ModelArtifact).where(ModelArtifact.tenant_id == auth.tenant_id, ModelArtifact.scope == "tenant"))
    for a in prev.scalars().all():
        a.is_active = False
    auth.tenant.active_model_id = None
    await db.commit()
    invalidate_tenant_cache(slug)
    return {"message": f"Tenant {slug} voltou ao modelo base", "active_model": "base"}
