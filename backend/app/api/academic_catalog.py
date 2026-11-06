"""Native academic catalog and class-record management — Wave 2.

Creates catalog entries in one tenant-scoped transaction, without arbitrary SQL
fields or external Frappe dependencies. All publication requires a separate
explicit human approval and is append-only audited.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.native_academic import _require_ies
from app.core.auth import AuthContext, require_permission
from app.core.config import get_settings
from app.db.session import get_db
from app.models.academic_catalog import (
    AcademicProgram, AcademicSubject, AcademicTeacher, AcademicTerm,
    AcademicClass, AcademicClassEnrollment, AcademicLesson,
    AcademicAttendance, AcademicAssessment, AcademicGrade,
    AcademicCalendarEvent, AcademicCatalogAudit,
)

router = APIRouter(prefix="/native-academic/catalog", tags=["Catálogo acadêmico nativo"])

ModelUUID = UUID
KindStatus = Literal["active", "inactive"]
RecordPublication = Literal["draft", "published"]


def _enabled() -> None:
    settings = get_settings()
    if not settings.native_academic_enabled or not settings.native_academic_catalog_enabled:
        raise HTTPException(status_code=503, detail="Catálogo acadêmico em homologação.")


def _human(auth: AuthContext) -> None:
    if not auth.user_id or not auth.session_id:
        raise HTTPException(status_code=403, detail="Ação restrita a usuário institucional autenticado.")


class ProgramInput(BaseModel):
    id: ModelUUID = Field(default_factory=uuid4)
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=180)
    modality: str | None = Field(default=None, max_length=48)
    status: KindStatus = "active"


class SubjectInput(BaseModel):
    id: ModelUUID = Field(default_factory=uuid4)
    program_id: ModelUUID
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=180)
    credit_hours: int | None = Field(default=None, ge=1, le=10000)
    status: KindStatus = "active"


class TeacherInput(BaseModel):
    id: ModelUUID = Field(default_factory=uuid4)
    staff_code: str = Field(min_length=1, max_length=60)
    display_name: str = Field(min_length=2, max_length=180)
    department: str | None = Field(default=None, max_length=120)
    status: KindStatus = "active"


class TermInput(BaseModel):
    id: ModelUUID = Field(default_factory=uuid4)
    code: str = Field(min_length=1, max_length=40)
    label: str = Field(min_length=1, max_length=100)
    starts_on: date
    ends_on: date
    status: Literal["planned", "active", "completed"] = "planned"

    @model_validator(mode="after")
    def valid_dates(self):
        if self.ends_on < self.starts_on:
            raise ValueError("Data final do período anterior ao início.")
        return self


class ClassInput(BaseModel):
    id: ModelUUID = Field(default_factory=uuid4)
    subject_id: ModelUUID
    term_id: ModelUUID
    teacher_id: ModelUUID | None = None
    code: str = Field(min_length=1, max_length=60)
    campus: str | None = Field(default=None, max_length=120)
    status: Literal["planned", "active", "completed", "cancelled"] = "planned"
    capacity: int | None = Field(default=None, ge=1, le=10000)


class EnrollmentInput(BaseModel):
    id: ModelUUID = Field(default_factory=uuid4)
    class_id: ModelUUID
    student_id: ModelUUID
    status: Literal["enrolled", "completed", "dropped"] = "enrolled"
    enrolled_on: date


class LessonInput(BaseModel):
    id: ModelUUID = Field(default_factory=uuid4)
    class_id: ModelUUID
    starts_at: datetime
    ends_at: datetime
    topic: str | None = Field(default=None, max_length=200)
    room: str | None = Field(default=None, max_length=120)

    @model_validator(mode="after")
    def valid_duration(self):
        if (self.starts_at.tzinfo is None or self.ends_at.tzinfo is None
                or self.ends_at <= self.starts_at):
            raise ValueError("Aula exige horários com fuso e fim posterior ao início.")
        return self


class AttendanceInput(BaseModel):
    id: ModelUUID = Field(default_factory=uuid4)
    class_id: ModelUUID
    lesson_id: ModelUUID
    student_id: ModelUUID
    status: Literal["present", "absent", "excused", "unrecorded"] = "unrecorded"


class AssessmentInput(BaseModel):
    id: ModelUUID = Field(default_factory=uuid4)
    class_id: ModelUUID
    code: str = Field(min_length=1, max_length=50)
    title: str = Field(min_length=1, max_length=180)
    max_score: Decimal = Field(gt=0, le=999999)


class GradeInput(BaseModel):
    id: ModelUUID = Field(default_factory=uuid4)
    class_id: ModelUUID
    assessment_id: ModelUUID
    student_id: ModelUUID
    score: Decimal = Field(ge=0, le=999999)


class CalendarInput(BaseModel):
    id: ModelUUID = Field(default_factory=uuid4)
    term_id: ModelUUID
    class_id: ModelUUID | None = None
    scope: Literal["institution", "class"]
    title: str = Field(min_length=1, max_length=180)
    starts_at: datetime
    ends_at: datetime
    location: str | None = Field(default=None, max_length=120)

    @model_validator(mode="after")
    def valid_scope(self):
        if (self.starts_at.tzinfo is None or self.ends_at.tzinfo is None
                or self.ends_at <= self.starts_at):
            raise ValueError("Evento exige horários válidos e com fuso.")
        if (self.scope == "institution" and self.class_id is not None
                or self.scope == "class" and self.class_id is None):
            raise ValueError("Eventos da turma exigem turma; gerais não aceitam turma.")
        return self


class CatalogBatch(BaseModel):
    programs: list[ProgramInput] = Field(default_factory=list, max_length=80)
    subjects: list[SubjectInput] = Field(default_factory=list, max_length=120)
    teachers: list[TeacherInput] = Field(default_factory=list, max_length=80)
    terms: list[TermInput] = Field(default_factory=list, max_length=80)
    classes: list[ClassInput] = Field(default_factory=list, max_length=120)
    enrollments: list[EnrollmentInput] = Field(default_factory=list, max_length=300)
    lessons: list[LessonInput] = Field(default_factory=list, max_length=150)
    attendance: list[AttendanceInput] = Field(default_factory=list, max_length=500)
    assessments: list[AssessmentInput] = Field(default_factory=list, max_length=100)
    grades: list[GradeInput] = Field(default_factory=list, max_length=500)
    calendar_events: list[CalendarInput] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def max_transaction(self):
        total = sum(len(getattr(self, key)) for key, _ in TABLE_MODELS)
        if total < 1 or total > 500:
            raise ValueError("Lote deve conter entre 1 e 500 registros.")
        ids = [item.id for key, _ in TABLE_MODELS for item in getattr(self, key)]
        if len(ids) != len(set(ids)):
            raise ValueError("IDs duplicados no lote.")
        return self


TABLE_MODELS = (
    ("programs", AcademicProgram),
    ("subjects", AcademicSubject),
    ("teachers", AcademicTeacher),
    ("terms", AcademicTerm),
    ("classes", AcademicClass),
    ("enrollments", AcademicClassEnrollment),
    ("lessons", AcademicLesson),
    ("attendance", AcademicAttendance),
    ("assessments", AcademicAssessment),
    ("grades", AcademicGrade),
    ("calendar_events", AcademicCalendarEvent),
)


def _fields(item: BaseModel) -> dict:
    # Pydantic only permits the allowlisted per-entity fields defined above.
    return {
        key: str(value) if isinstance(value, UUID) else value
        for key, value in item.model_dump(exclude_none=True).items()
    }


@router.get("/overview")
async def catalog_overview(
    auth: AuthContext = Depends(require_permission("students.sensitive.view")),
    db: AsyncSession = Depends(get_db),
):
    _enabled()
    _human(auth)
    await _require_ies(db, auth)
    counts = {}
    for key, model in TABLE_MODELS:
        counts[key] = (await db.execute(select(func.count()).select_from(model).where(
            model.tenant_id == auth.tenant_id,
        ))).scalar_one()
    programs = (await db.execute(select(AcademicProgram).where(
        AcademicProgram.tenant_id == auth.tenant_id,
    ).order_by(AcademicProgram.name).limit(50))).scalars().all()
    terms = (await db.execute(select(AcademicTerm).where(
        AcademicTerm.tenant_id == auth.tenant_id,
    ).order_by(AcademicTerm.starts_on.desc()).limit(50))).scalars().all()
    subjects = (await db.execute(select(AcademicSubject).where(
        AcademicSubject.tenant_id == auth.tenant_id,
    ).order_by(AcademicSubject.name).limit(100))).scalars().all()
    teachers = (await db.execute(select(AcademicTeacher).where(
        AcademicTeacher.tenant_id == auth.tenant_id,
    ).order_by(AcademicTeacher.display_name).limit(100))).scalars().all()
    classes = (await db.execute(select(AcademicClass).where(
        AcademicClass.tenant_id == auth.tenant_id,
    ).order_by(AcademicClass.code).limit(100))).scalars().all()
    return {
        "backend": "mira_native", "counts": counts,
        "programs": [{"id": p.id, "code": p.code, "name": p.name,
                      "modality": p.modality, "status": p.status} for p in programs],
        "terms": [{"id": t.id, "code": t.code, "label": t.label,
                   "starts_on": t.starts_on.isoformat(), "ends_on": t.ends_on.isoformat(),
                   "status": t.status} for t in terms],
        "subjects": [{"id": s.id, "code": s.code, "name": s.name,
                      "program_id": s.program_id, "credit_hours": s.credit_hours,
                      "status": s.status} for s in subjects],
        "teachers": [{"id": teacher.id, "display_name": teacher.display_name,
                      "department": teacher.department,
                      "status": teacher.status} for teacher in teachers],
        "classes": [{"id": c.id, "code": c.code, "subject_id": c.subject_id,
                     "term_id": c.term_id, "teacher_id": c.teacher_id,
                     "status": c.status} for c in classes],
        "preview_limited": any(counts[key] > limit for key, limit in (
            ("programs", 50), ("terms", 50), ("subjects", 100),
            ("teachers", 100), ("classes", 100),
        )),
    }


@router.post("/batch", status_code=201)
async def create_catalog_batch(
    body: CatalogBatch,
    auth: AuthContext = Depends(require_permission("settings.manage")),
    db: AsyncSession = Depends(get_db),
):
    """Staff-only, all-or-nothing import with tenant PK/FKs and draft publication."""
    _enabled()
    _human(auth)
    await _require_ies(db, auth)
    if get_settings().native_academic_operations_enabled:
        if body.enrollments or body.grades or body.attendance:
            raise HTTPException(
                status_code=409,
                detail="Use a operação acadêmica versionada para matrícula, notas e frequência.",
            )
        class_ids = {str(item.class_id) for item in (*body.lessons, *body.assessments)}
        if class_ids:
            existing = (await db.execute(select(AcademicClass).where(
                AcademicClass.tenant_id == auth.tenant_id, AcademicClass.id.in_(class_ids),
            ))).scalars().all()
            if any(item.status == "completed" for item in existing):
                raise HTTPException(status_code=409, detail="Turma concluída não aceita novas aulas ou avaliações.")
    counts = {}
    try:
        for key, model in TABLE_MODELS:
            items = getattr(body, key)
            counts[key] = len(items)
            for item in items:
                row = model(tenant_id=auth.tenant_id, **_fields(item))
                db.add(row)
            # Foreign keys may refer to other entities from the same batch.
            await db.flush()
        # Reject grades above the matching assessment max score, even when
        # the model came from a different operation in this same transaction.
        for grade in body.grades:
            assessment = (await db.execute(select(AcademicAssessment).where(
                AcademicAssessment.id == str(grade.assessment_id),
                AcademicAssessment.tenant_id == auth.tenant_id,
                AcademicAssessment.class_id == str(grade.class_id),
            ))).scalar_one_or_none()
            if assessment is None or grade.score > assessment.max_score:
                raise HTTPException(status_code=422, detail="Nota excede a avaliação da turma.")
        db.add(AcademicCatalogAudit(
            tenant_id=auth.tenant_id, actor_user_id=auth.user_id,
            action="batch_import", counts=counts,
        ))
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Conflito de código, vínculo ou referência. Verifique a instituição e os registros.",
        ) from None
    except Exception:
        await db.rollback()
        raise
    return {"created": counts, "published": False, "notifications_sent": False}


@router.get("/drafts")
async def catalog_drafts(
    auth: AuthContext = Depends(require_permission("students.sensitive.view")),
    db: AsyncSession = Depends(get_db),
):
    _enabled()
    _human(auth)
    await _require_ies(db, auth)
    pending = []
    for key, model in PUBLISHABLE.items():
        rows = (await db.execute(select(model).where(
            model.tenant_id == auth.tenant_id,
            model.publication_status == "draft",
        ).order_by(model.id).limit(50))).scalars().all()
        for row in rows:
            pending.append({
                "id": row.id, "resource": key,
                "title": (getattr(row, "title", None) or
                          getattr(row, "topic", None) or
                          "Registro pendente"),
                "class_id": getattr(row, "class_id", None),
            })
    return {"items": pending, "per_category_limit": 50}


PUBLISHABLE = {
    "lessons": AcademicLesson,
    "assessments": AcademicAssessment,
    "grades": AcademicGrade,
    "calendar_events": AcademicCalendarEvent,
}


@router.post("/{resource}/{record_id}/publish")
async def publish_catalog_record(
    resource: str, record_id: UUID,
    auth: AuthContext = Depends(require_permission("critical.manage")),
    db: AsyncSession = Depends(get_db),
):
    """Explicit approval; grade publication additionally requires a published assessment."""
    _enabled()
    _human(auth)
    await _require_ies(db, auth)
    model = PUBLISHABLE.get(resource)
    if model is None:
        raise HTTPException(status_code=404, detail="Recurso não publicável.")
    record = (await db.execute(select(model).where(
        model.id == str(record_id), model.tenant_id == auth.tenant_id,
    ).with_for_update())).scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Registro não encontrado.")
    if get_settings().native_academic_operations_enabled and isinstance(record, (AcademicGrade, AcademicAssessment, AcademicLesson)):
        parent = (await db.execute(select(AcademicClass).where(
            AcademicClass.tenant_id == auth.tenant_id, AcademicClass.id == record.class_id,
        ))).scalar_one_or_none()
        if parent is None or parent.status == "completed":
            raise HTTPException(status_code=409, detail="Turma concluída não permite novas publicações.")
    if isinstance(record, AcademicGrade):
        assessment = (await db.execute(select(AcademicAssessment).where(
            AcademicAssessment.id == record.assessment_id,
            AcademicAssessment.tenant_id == auth.tenant_id,
            AcademicAssessment.class_id == record.class_id,
        ))).scalar_one_or_none()
        if not assessment or assessment.publication_status != "published" or record.score > assessment.max_score:
            raise HTTPException(status_code=409, detail="A avaliação deve estar publicada com nota válida.")
    if record.publication_status != "published":
        record.publication_status = "published"
        db.add(AcademicCatalogAudit(
            tenant_id=auth.tenant_id, actor_user_id=auth.user_id,
            action=f"publish:{resource}", counts={"records": 1},
        ))
        await db.commit()
    return {"id": record.id, "publication_status": record.publication_status,
            "notifications_sent": False}
