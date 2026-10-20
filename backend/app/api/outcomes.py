"""Outcomes e learning loop — protegido por X-API-Key."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
import hmac
import secrets
from fastapi import APIRouter, Depends, HTTPException, Query, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, Field

from app.db.session import get_db
from app.models.tenant import Tenant, TrainingEvent, ModelArtifact
from app.models.student import Student
from app.services.tenant import get_tenant_learning_stats, ensure_base_model_registered
from app.ml.tenant_train import train_tenant_model, invalidate_tenant_cache
from app.core.auth import AuthContext, get_current_tenant, require_tenant_match
from app.core.security import generate_api_key, hash_api_key
from app.core.config import get_settings

router = APIRouter()

OUTCOME_TO_LABEL = {
    "evadiu": 1, "trancou": 1, "transferiu": 1,
    "concluiu": 0, "ativo": 0, "formou": 0,
}


class OutcomeItem(BaseModel):
    matricula: str
    outcome: str
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
    updated = created = 0
    errors = []
    for item in body.outcomes:
        outcome_key = item.outcome.strip().lower()
        if outcome_key not in OUTCOME_TO_LABEL:
            errors.append({"matricula": item.matricula, "error": f"outcome invalido: {item.outcome}"})
            continue
        label = OUTCOME_TO_LABEL[outcome_key]
        event = None
        if item.training_event_id:
            r = await db.execute(select(TrainingEvent).where(TrainingEvent.id == item.training_event_id, TrainingEvent.tenant_id == tenant.id))
            event = r.scalar_one_or_none()
        if not event:
            r = await db.execute(select(TrainingEvent).where(TrainingEvent.tenant_id == tenant.id, TrainingEvent.matricula == item.matricula, TrainingEvent.label.is_(None)).order_by(TrainingEvent.scored_at.desc()).limit(1))
            event = r.scalar_one_or_none()
        if not event:
            r = await db.execute(select(TrainingEvent).where(TrainingEvent.tenant_id == tenant.id, TrainingEvent.matricula == item.matricula).order_by(TrainingEvent.scored_at.desc()).limit(1))
            event = r.scalar_one_or_none()
        if event:
            event.label = label
            event.outcome = outcome_key
            event.labeled_at = now
            event.outcome_notes = item.notes
            updated += 1
        else:
            student = None
            if item.student_id:
                r = await db.execute(select(Student).where(Student.id == item.student_id, Student.tenant_id == tenant.id))
                student = r.scalar_one_or_none()
            if not student:
                r = await db.execute(select(Student).where(Student.matricula == item.matricula, Student.tenant_id == tenant.id).order_by(Student.created_at.desc()).limit(1))
                student = r.scalar_one_or_none()
            features = {}
            if student:
                features = {"dias_atraso_boleto": student.dias_atraso_boleto or 0, "recorrencia_atrasos": student.recorrencia_atrasos or 0,
                    "dias_sem_login": student.dias_sem_login or 0, "presenca_percentual": student.presenca_percentual or 100.0,
                    "nota_media": student.nota_media or 7.0, "reprovacoes": student.reprovacoes or 0, "semestre": student.semestre or 3}
            db.add(TrainingEvent(tenant_id=tenant.id, student_id=student.id if student else None,
                batch_id=student.batch_id if student else None, matricula=item.matricula, features_snapshot=features,
                model_score=student.risk_score if student else None, adjusted_score=student.risk_score if student else None,
                risk_level=student.risk_level if student else None, model_version="0.3.4", model_scope="base",
                label=label, outcome=outcome_key, labeled_at=now, outcome_notes=item.notes))
            created += 1
    await db.flush()
    stats = await get_tenant_learning_stats(db, tenant.id)
    await db.commit()
    return {"message": f"{updated} outcomes atualizados, {created} eventos criados", "updated": updated, "created": created, "errors": errors, "learning": stats}


@router.get("/training-events")
async def list_training_events(
    tenant_slug: str = Query("default"), labeled_only: bool = Query(False),
    limit: int = Query(50, ge=1, le=500),
    auth: AuthContext = Depends(get_current_tenant), db: AsyncSession = Depends(get_db),
):
    await require_tenant_match(auth, tenant_slug)
    q = select(TrainingEvent).where(TrainingEvent.tenant_id == auth.tenant_id)
    if labeled_only:
        q = q.where(TrainingEvent.label.is_not(None))
    q = q.order_by(TrainingEvent.scored_at.desc()).limit(limit)
    events = (await db.execute(q)).scalars().all()
    return {"tenant": auth.tenant_slug, "count": len(events), "events": [{
        "id": e.id, "matricula": e.matricula, "scored_at": e.scored_at, "adjusted_score": e.adjusted_score,
        "risk_level": e.risk_level, "label": e.label, "outcome": e.outcome, "labeled_at": e.labeled_at,
        "model_scope": e.model_scope,
    } for e in events]}


@router.post("/tenants/{slug}/train")
async def train_tenant_endpoint(
    slug: str, force: bool = Query(False), force_activate: bool = Query(False),
    auth: AuthContext = Depends(get_current_tenant), db: AsyncSession = Depends(get_db),
):
    await require_tenant_match(auth, slug)
    try:
        return await train_tenant_model(db, tenant_slug=auth.tenant_slug, force=force, force_activate=force_activate)
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
    return {"tenant": slug, "active_model_id": auth.tenant.active_model_id, "models": [{
        "id": a.id, "name": a.name, "version": a.version, "scope": a.scope,
        "is_active": a.is_active, "metrics": a.metrics, "trained_at": a.trained_at,
    } for a in arts]}


@router.post("/tenants/{slug}/models/{artifact_id}/activate")
async def activate_tenant_model(slug: str, artifact_id: str, auth: AuthContext = Depends(get_current_tenant), db: AsyncSession = Depends(get_db)):
    await require_tenant_match(auth, slug)
    r = await db.execute(select(ModelArtifact).where(ModelArtifact.id == artifact_id, ModelArtifact.tenant_id == auth.tenant_id))
    art = r.scalar_one_or_none()
    if not art:
        raise HTTPException(status_code=404, detail="Artefato nao encontrado")
    prev = await db.execute(select(ModelArtifact).where(ModelArtifact.tenant_id == auth.tenant_id, ModelArtifact.scope == "tenant"))
    for a in prev.scalars().all():
        a.is_active = a.id == artifact_id
    art.is_active = True
    auth.tenant.active_model_id = art.id
    await db.commit()
    invalidate_tenant_cache(slug)
    return {"message": f"Modelo {art.version} ativado", "artifact_id": art.id}


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
