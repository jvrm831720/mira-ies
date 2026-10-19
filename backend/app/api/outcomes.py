"""Outcomes e learning loop — fecha o ciclo supervisionado do Modelo Hibrido C."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, Field

from app.db.session import get_db
from app.models.tenant import Tenant, TrainingEvent
from app.models.student import Student
from app.services.tenant import (
    get_or_create_tenant,
    get_tenant_learning_stats,
    ensure_base_model_registered,
)

router = APIRouter()

OUTCOME_TO_LABEL = {
    "evadiu": 1, "trancou": 1, "transferiu": 1,
    "concluiu": 0, "ativo": 0, "formou": 0,
}


class OutcomeItem(BaseModel):
    matricula: str
    outcome: str = Field(..., description="evadiu | trancou | concluiu | transferiu | ativo | formou")
    notes: Optional[str] = None
    student_id: Optional[str] = None
    training_event_id: Optional[str] = None


class OutcomeBatchRequest(BaseModel):
    tenant_slug: str = "default"
    outcomes: list[OutcomeItem] = Field(..., min_length=1)


class TenantCreateRequest(BaseModel):
    slug: str = Field(..., min_length=2, max_length=80)
    name: str
    segment: Optional[str] = None


@router.post("/tenants", status_code=201)
async def create_tenant(body: TenantCreateRequest, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(Tenant).where(Tenant.slug == body.slug))
    t = existing.scalar_one_or_none()
    if t:
        return {"id": t.id, "slug": t.slug, "name": t.name, "message": "Tenant ja existia"}
    t = Tenant(slug=body.slug, name=body.name, segment=body.segment, is_active=True)
    db.add(t)
    await ensure_base_model_registered(db)
    await db.commit()
    await db.refresh(t)
    return {"id": t.id, "slug": t.slug, "name": t.name, "message": "Tenant criado"}


@router.get("/tenants")
async def list_tenants(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Tenant).order_by(Tenant.created_at.desc()))
    tenants = result.scalars().all()
    return {
        "count": len(tenants),
        "tenants": [{
            "id": t.id, "slug": t.slug, "name": t.name, "segment": t.segment,
            "labeled_events": t.labeled_events_count,
            "positive_labels": t.positive_labels_count,
            "tenant_model_ready": t.tenant_model_ready,
        } for t in tenants],
    }


@router.get("/tenants/{slug}/learning")
async def tenant_learning_status(slug: str, db: AsyncSession = Depends(get_db)):
    tenant = await get_or_create_tenant(db, slug=slug)
    await db.commit()
    stats = await get_tenant_learning_stats(db, tenant.id)
    await db.commit()
    return stats


@router.post("/outcomes", status_code=201)
async def register_outcomes(body: OutcomeBatchRequest, db: AsyncSession = Depends(get_db)):
    tenant = await get_or_create_tenant(db, slug=body.tenant_slug)
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
            r = await db.execute(select(TrainingEvent).where(
                TrainingEvent.id == item.training_event_id, TrainingEvent.tenant_id == tenant.id))
            event = r.scalar_one_or_none()
        if not event:
            r = await db.execute(select(TrainingEvent).where(
                TrainingEvent.tenant_id == tenant.id, TrainingEvent.matricula == item.matricula,
                TrainingEvent.label.is_(None),
            ).order_by(TrainingEvent.scored_at.desc()).limit(1))
            event = r.scalar_one_or_none()
        if not event:
            r = await db.execute(select(TrainingEvent).where(
                TrainingEvent.tenant_id == tenant.id, TrainingEvent.matricula == item.matricula,
            ).order_by(TrainingEvent.scored_at.desc()).limit(1))
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
                r = await db.execute(select(Student).where(Student.id == item.student_id))
                student = r.scalar_one_or_none()
            if not student:
                r = await db.execute(select(Student).where(Student.matricula == item.matricula)
                    .order_by(Student.created_at.desc()).limit(1))
                student = r.scalar_one_or_none()
            features = {}
            if student:
                features = {
                    "dias_atraso_boleto": student.dias_atraso_boleto or 0,
                    "recorrencia_atrasos": student.recorrencia_atrasos or 0,
                    "dias_sem_login": student.dias_sem_login or 0,
                    "presenca_percentual": student.presenca_percentual or 100.0,
                    "nota_media": student.nota_media or 7.0,
                    "reprovacoes": student.reprovacoes or 0,
                    "semestre": student.semestre or 3,
                }
            db.add(TrainingEvent(
                tenant_id=tenant.id,
                student_id=student.id if student else None,
                batch_id=student.batch_id if student else None,
                matricula=item.matricula,
                features_snapshot=features,
                model_score=student.risk_score if student else None,
                adjusted_score=student.risk_score if student else None,
                risk_level=student.risk_level if student else None,
                model_version="0.3.1", model_scope="base",
                label=label, outcome=outcome_key, labeled_at=now, outcome_notes=item.notes,
            ))
            created += 1

    await db.flush()
    stats = await get_tenant_learning_stats(db, tenant.id)
    await db.commit()
    return {
        "message": f"{updated} outcomes atualizados, {created} eventos criados",
        "updated": updated, "created": created, "errors": errors, "learning": stats,
    }


@router.get("/training-events")
async def list_training_events(
    tenant_slug: str = Query("default"),
    labeled_only: bool = Query(False),
    limit: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    tenant = await get_or_create_tenant(db, slug=tenant_slug)
    q = select(TrainingEvent).where(TrainingEvent.tenant_id == tenant.id)
    if labeled_only:
        q = q.where(TrainingEvent.label.is_not(None))
    q = q.order_by(TrainingEvent.scored_at.desc()).limit(limit)
    result = await db.execute(q)
    events = result.scalars().all()
    await db.commit()
    return {
        "tenant": tenant.slug,
        "count": len(events),
        "events": [{
            "id": e.id, "matricula": e.matricula, "scored_at": e.scored_at,
            "adjusted_score": e.adjusted_score, "risk_level": e.risk_level,
            "label": e.label, "outcome": e.outcome, "labeled_at": e.labeled_at,
            "model_scope": e.model_scope,
        } for e in events],
    }
