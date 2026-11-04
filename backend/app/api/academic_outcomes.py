"""Tenant-scoped ingestion of confirmed academic outcomes from SIS/ERP sources."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthContext, get_current_tenant
from app.db.session import get_db
from app.ml.targets import SUPPORTED_OUTCOMES, TARGET_DEFINITION_VERSION, derive_target_label, normalize_utc_timestamp
from app.models.educational_outcome import AcademicOutcome
from app.models.intervention import InterventionLog
from app.models.student import Student
from app.models.tenant import TrainingEvent

router = APIRouter()


class AcademicOutcomeItem(BaseModel):
    matricula: str = Field(..., min_length=1, max_length=50)
    outcome: str = Field(..., min_length=1, max_length=40)
    observed_at: datetime
    academic_period: Optional[str] = Field(default=None, max_length=40)
    source: str = Field(default="manual", min_length=1, max_length=80)
    source_record_id: Optional[str] = Field(default=None, max_length=160)
    student_id: Optional[str] = None
    course: Optional[str] = Field(default=None, max_length=150)


class AcademicOutcomeBatch(BaseModel):
    outcomes: list[AcademicOutcomeItem] = Field(..., min_length=1, max_length=2000)


@router.post("/academic-outcomes", status_code=201)
async def import_academic_outcomes(
    body: AcademicOutcomeBatch,
    auth: AuthContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Import SIS-confirmed outcomes independently from risk-scoring snapshots.

    Supplying a source_record_id makes repeated deliveries from the same source
    idempotent. When a compatible score snapshot exists, it is also labeled for
    the learning loop; its absence never blocks the academic outcome record.
    """
    now = datetime.now(timezone.utc)
    created = updated = linked_training_events = attributed_interventions = 0
    errors: list[dict[str, str]] = []

    for item in body.outcomes:
        matricula = item.matricula.strip()
        outcome = item.outcome.strip().lower()
        source = item.source.strip().lower()
        source_record_id = (item.source_record_id.strip() or None) if item.source_record_id else None
        academic_period = item.academic_period.strip() if item.academic_period else None
        observed_at = normalize_utc_timestamp(item.observed_at)

        if outcome not in SUPPORTED_OUTCOMES:
            errors.append({"matricula": matricula, "error": f"outcome inválido: {item.outcome}"})
            continue
        if not source:
            errors.append({"matricula": matricula, "error": "source não pode ser vazio"})
            continue
        if observed_at > now:
            errors.append({"matricula": matricula, "error": "observed_at não pode estar no futuro"})
            continue
        if not matricula:
            errors.append({"matricula": item.matricula, "error": "matricula não pode ser vazia"})
            continue

        student = None
        if item.student_id:
            result = await db.execute(
                select(Student).where(
                    Student.id == item.student_id,
                    Student.tenant_id == auth.tenant_id,
                )
            )
            student = result.scalar_one_or_none()
            if not student:
                errors.append({"matricula": matricula, "error": "student_id não encontrado para este tenant"})
                continue
            if student.matricula != matricula:
                errors.append({"matricula": matricula, "error": "student_id não corresponde à matrícula informada"})
                continue
        else:
            result = await db.execute(
                select(Student)
                .where(Student.tenant_id == auth.tenant_id, Student.matricula == matricula)
                .order_by(Student.updated_at.desc())
                .limit(1)
            )
            student = result.scalar_one_or_none()

        existing = None
        if source_record_id:
            result = await db.execute(
                select(AcademicOutcome).where(
                    AcademicOutcome.tenant_id == auth.tenant_id,
                    AcademicOutcome.source == source,
                    AcademicOutcome.source_record_id == source_record_id,
                )
            )
            existing = result.scalar_one_or_none()
            if existing and existing.matricula != matricula:
                errors.append({"matricula": matricula, "error": "source_record_id já pertence a outra matrícula"})
                continue

        values = {
            "tenant_id": auth.tenant_id,
            "student_id": student.id if student else None,
            "matricula": matricula,
            "course": (item.course.strip() if item.course else None) or (student.curso if student else None),
            "academic_period": academic_period or None,
            "outcome": outcome,
            "observed_at": observed_at,
            "source": source,
            "source_record_id": source_record_id,
        }
        if existing:
            for key, value in values.items():
                if key != "tenant_id":
                    setattr(existing, key, value)
            existing.updated_at = now
            updated += 1
        else:
            db.add(AcademicOutcome(**values))
            created += 1

        # Keep the learning loop in sync when a compatible, pre-outcome score exists.
        score_result = await db.execute(
            select(TrainingEvent)
            .where(
                TrainingEvent.tenant_id == auth.tenant_id,
                TrainingEvent.matricula == matricula,
                TrainingEvent.scored_at <= observed_at,
            )
            .order_by(TrainingEvent.scored_at.desc())
            .limit(1)
        )
        training_event = score_result.scalar_one_or_none()
        if training_event:
            try:
                label, _label_status = derive_target_label(outcome, training_event.scored_at, observed_at)
            except ValueError:
                label = None
            training_event.outcome = outcome
            training_event.outcome_at = observed_at
            training_event.outcome_period = academic_period or None
            training_event.outcome_source = source[:40]
            training_event.labeled_at = now
            training_event.label = label
            training_event.target_definition = TARGET_DEFINITION_VERSION if label is not None else None
            linked_training_events += 1

        final_status = {
            "rematriculado": "stayed", "ativo": "stayed", "concluiu": "stayed", "formou": "stayed",
            "evadiu": "dropped", "trancou": "dropped", "transferiu": "transferred",
        }.get(outcome)
        if final_status:
            attributed = await db.execute(
                update(InterventionLog)
                .where(
                    InterventionLog.tenant_id == auth.tenant_id,
                    InterventionLog.matricula == matricula,
                    InterventionLog.status == "sent",
                    InterventionLog.outcome.is_(None),
                    InterventionLog.created_at >= observed_at - timedelta(days=90),
                    InterventionLog.created_at <= observed_at,
                )
                .values(
                    outcome=final_status,
                    outcome_at=observed_at,
                    outcome_source="academic_import",
                    outcome_note=f"Desfecho acadêmico {outcome} importado de {source}"[:240],
                )
            )
            attributed_interventions += max(0, attributed.rowcount or 0)

    await db.commit()
    return {
        "created": created,
        "updated": updated,
        "linked_training_events": linked_training_events,
        "attributed_interventions": attributed_interventions,
        "errors": errors,
        "outcomes_received": len(body.outcomes),
        "message": "Outcomes acadêmicos confirmados registrados; outcomes sem snapshot de risco também são preservados.",
    }
