"""Wave 6: operational enrollment, curriculum, gradebook, attendance and transcript.

Safe by default. No billing, payment, external messages or automatic academic
decisions; every institutional decision requires a signed human session.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import and_, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.native_academic import PortalIdentity, _portal_action, _portal_identity, _require_ies, _student
from app.core.auth import AuthContext, require_permission
from app.core.config import get_settings
from app.db.session import get_db
from app.models.academic_catalog import (
    AcademicAssessment, AcademicAttendance, AcademicClass, AcademicClassEnrollment,
    AcademicGrade, AcademicLesson, AcademicProgram, AcademicSubject, AcademicTerm,
)
from app.models.academic_operations import (
    AcademicClassOutcome, AcademicCurriculum, AcademicCurriculumItem,
    AcademicEnrollmentRequest, AcademicEnrollmentRequestClass,
    AcademicOperationEvent, AcademicPolicy, AcademicStudentProgram,
)
from app.models.student import Student
from app.models.tenant import Tenant
from app.services.academic_operations import (
    AcademicRuleViolation, calculate_result, enrollment_in_window,
    policy_snapshot, validate_curriculum_graph,
)

institution_router = APIRouter(prefix="/native-academic/operations", tags=["Operação acadêmica — Wave 6"])
portal_router = APIRouter(prefix="/student-portal/academic-operations", tags=["Jornada acadêmica do aluno"])
CLOSED = frozenset(("completed", "cancelled"))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _enabled() -> None:
    flags = get_settings()
    if not (flags.native_academic_enabled and flags.native_academic_catalog_enabled
            and flags.native_academic_operations_enabled):
        raise HTTPException(status_code=503, detail="Operação acadêmica em homologação.")


async def _staff(db: AsyncSession, auth: AuthContext):
    _enabled()
    if not auth.user_id or not auth.session_id or auth.aal < 2:
        raise HTTPException(status_code=403, detail="Operação exige sessão institucional MFA AAL2.")
    await _require_ies(db, auth)


def _event(db: AsyncSession, tenant_id: str, actor: str, user_id: str | None,
           event: str, kind: str, target_id: str, data: dict | None = None):
    db.add(AcademicOperationEvent(
        tenant_id=tenant_id, actor_kind=actor, actor_user_id=user_id,
        event_type=event, target_kind=kind, target_id=target_id,
        details=data or {},
    ))


def _missing(label: str = "Registro acadêmico não encontrado."):
    raise HTTPException(status_code=404, detail=label)


def _conflict(message: str):
    raise HTTPException(status_code=409, detail=message)


async def _row(db: AsyncSession, model, tenant_id: str, id: UUID | str, *, lock=False):
    q = select(model).where(model.tenant_id == tenant_id, model.id == str(id))
    if lock:
        q = q.with_for_update()
    found = (await db.execute(q)).scalar_one_or_none()
    if found is None:
        _missing()
    return found


async def _policy(db: AsyncSession, tenant_id: str) -> AcademicPolicy:
    result = (await db.execute(select(AcademicPolicy).where(
        AcademicPolicy.tenant_id == tenant_id,
        AcademicPolicy.status == "published",
    ).order_by(AcademicPolicy.version.desc()).limit(1))).scalar_one_or_none()
    if result is None:
        _conflict("A instituição precisa publicar suas regras acadêmicas antes de operar.")
    return result


class PolicyInput(BaseModel):
    passing_percent: Decimal = Field(ge=0, le=100, decimal_places=2)
    min_attendance_percent: Decimal = Field(ge=0, le=100, decimal_places=2)
    max_classes_per_term: int = Field(ge=1, le=30)
    excused_excluded: bool = True
    allow_reenrollment: bool = True
    enrollment_opens_on: date | None = None
    enrollment_closes_on: date | None = None

    @model_validator(mode="after")
    def validate_window(self):
        if (self.enrollment_opens_on and self.enrollment_closes_on and
                self.enrollment_closes_on < self.enrollment_opens_on):
            raise ValueError("Fim da janela anterior ao início.")
        return self


class CurriculumItemInput(BaseModel):
    subject_id: UUID
    period_number: int = Field(ge=1, le=30)
    required: bool = True
    prerequisite_subject_id: UUID | None = None


class CurriculumInput(BaseModel):
    program_id: UUID
    code: str = Field(min_length=2, max_length=40)
    label: str = Field(min_length=3, max_length=160)
    items: list[CurriculumItemInput] = Field(min_length=1, max_length=200)


class StudentProgramInput(BaseModel):
    student_id: UUID
    program_id: UUID
    curriculum_id: UUID


class OfferInput(BaseModel):
    capacity: int | None = Field(default=None, ge=1, le=10000)
    enrollment_open: bool


class EnrollmentInput(BaseModel):
    student_program_id: UUID
    term_id: UUID
    class_ids: list[UUID] = Field(min_length=1, max_length=30)


class DecisionInput(BaseModel):
    approve: bool
    note: str = Field(min_length=3, max_length=500)


class GradeEntry(BaseModel):
    student_id: UUID
    score: Decimal = Field(ge=0, le=999999, decimal_places=2)


class GradeBatch(BaseModel):
    assessment_id: UUID
    entries: list[GradeEntry] = Field(min_length=1, max_length=250)


class AttendanceEntry(BaseModel):
    student_id: UUID
    status: Literal["present", "absent", "excused"]


class AttendanceBatch(BaseModel):
    lesson_id: UUID
    entries: list[AttendanceEntry] = Field(min_length=1, max_length=250)


def _request_json(r: AcademicEnrollmentRequest) -> dict:
    return {
        "id": r.id, "student_program_id": r.student_program_id,
        "term_id": r.term_id, "kind": r.kind, "status": r.status,
        "requested_by": r.requested_by,
        "submitted_at": r.submitted_at.isoformat(),
        "decided_at": r.decided_at.isoformat() if r.decided_at else None,
        "decision_note": r.decision_note,
        "policy_snapshot": r.policy_snapshot,
    }


@institution_router.get("/overview")
async def overview(
    auth: AuthContext = Depends(require_permission("students.sensitive.view")),
    db: AsyncSession = Depends(get_db),
):
    await _staff(db, auth)
    policy = (await db.execute(select(AcademicPolicy).where(
        AcademicPolicy.tenant_id == auth.tenant_id,
    ).order_by(AcademicPolicy.version.desc()).limit(20))).scalars().all()
    curr = (await db.execute(select(AcademicCurriculum).where(
        AcademicCurriculum.tenant_id == auth.tenant_id,
    ).order_by(AcademicCurriculum.created_at.desc()).limit(100))).scalars().all()
    programs = (await db.execute(select(AcademicProgram).where(
        AcademicProgram.tenant_id == auth.tenant_id,
    ).order_by(AcademicProgram.name).limit(200))).scalars().all()
    subjects = (await db.execute(select(AcademicSubject).where(
        AcademicSubject.tenant_id == auth.tenant_id,
    ).order_by(AcademicSubject.name).limit(500))).scalars().all()
    terms = (await db.execute(select(AcademicTerm).where(
        AcademicTerm.tenant_id == auth.tenant_id,
    ).order_by(AcademicTerm.starts_on.desc()).limit(80))).scalars().all()
    classes = (await db.execute(select(AcademicClass).where(
        AcademicClass.tenant_id == auth.tenant_id,
    ).order_by(AcademicClass.code).limit(250))).scalars().all()
    counts = {}
    for key, model in (("enrollment_requests", AcademicEnrollmentRequest),
                       ("active_students", AcademicStudentProgram),
                       ("outcomes", AcademicClassOutcome)):
        stmt = select(func.count()).select_from(model).where(model.tenant_id == auth.tenant_id)
        if key == "enrollment_requests":
            stmt = stmt.where(AcademicEnrollmentRequest.status == "submitted")
        if key == "active_students":
            stmt = stmt.where(AcademicStudentProgram.status == "active")
        counts[key] = (await db.execute(stmt)).scalar_one()
    return {
        "counts": counts, "policies": [
            {"id": p.id, "status": p.status, **policy_snapshot(p)} for p in policy
        ], "curricula": [
            {"id": c.id, "program_id": c.program_id, "code": c.code, "label": c.label,
             "status": c.status} for c in curr
        ], "programs": [
            {"id": p.id, "code": p.code, "name": p.name, "status": p.status} for p in programs
        ], "subjects": [
            {"id": s.id, "program_id": s.program_id, "code": s.code, "name": s.name,
             "status": s.status} for s in subjects
        ], "terms": [
            {"id": t.id, "code": t.code, "label": t.label, "status": t.status,
             "starts_on": t.starts_on.isoformat(), "ends_on": t.ends_on.isoformat()} for t in terms
        ], "classes": [
            {"id": c.id, "subject_id": c.subject_id, "term_id": c.term_id,
             "code": c.code, "status": c.status, "enrollment_open": c.enrollment_open,
             "capacity": c.capacity} for c in classes
        ], "preview_limited": True,
    }


@institution_router.post("/policies", status_code=201)
async def create_policy(
    body: PolicyInput,
    auth: AuthContext = Depends(require_permission("settings.manage")),
    db: AsyncSession = Depends(get_db),
):
    await _staff(db, auth)
    # Serialize version assignment across concurrent administrators.
    await db.execute(select(Tenant.id).where(Tenant.id == auth.tenant_id).with_for_update())
    version = (await db.execute(select(func.coalesce(func.max(AcademicPolicy.version), 0)).where(
        AcademicPolicy.tenant_id == auth.tenant_id,
    ))).scalar_one() + 1
    row = AcademicPolicy(
        tenant_id=auth.tenant_id, version=version,
        created_by_user_id=auth.user_id, **body.model_dump(),
    )
    db.add(row)
    await db.flush()
    _event(db, auth.tenant_id, "staff", auth.user_id, "policy_created", "policy", row.id, {"version": version})
    await db.commit()
    return {"id": row.id, "version": version, "status": "draft"}


@institution_router.post("/policies/{policy_id}/publish")
async def publish_policy(
    policy_id: UUID,
    auth: AuthContext = Depends(require_permission("critical.manage")),
    db: AsyncSession = Depends(get_db),
):
    await _staff(db, auth)
    row = await _row(db, AcademicPolicy, auth.tenant_id, policy_id, lock=True)
    if row.status != "draft":
        _conflict("Somente regras em rascunho podem ser publicadas.")
    newest = (await db.execute(select(func.max(AcademicPolicy.version)).where(
        AcademicPolicy.tenant_id == auth.tenant_id,
    ))).scalar_one()
    if row.version != newest:
        _conflict("Uma versão mais recente já existe.")
    row.status = "published"
    row.published_at = _now()
    _event(db, auth.tenant_id, "staff", auth.user_id, "policy_published", "policy", row.id, {"version": row.version})
    await db.commit()
    return {"id": row.id, "status": "published", "version": row.version}


@institution_router.post("/curricula", status_code=201)
async def create_curriculum(
    body: CurriculumInput,
    auth: AuthContext = Depends(require_permission("settings.manage")),
    db: AsyncSession = Depends(get_db),
):
    await _staff(db, auth)
    program = await _row(db, AcademicProgram, auth.tenant_id, body.program_id)
    if program.status != "active":
        _conflict("Curso não está ativo.")
    graph = [item.model_dump(mode="json") for item in body.items]
    try:
        validate_curriculum_graph(graph)
    except AcademicRuleViolation as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    subjects = (await db.execute(select(AcademicSubject).where(
        AcademicSubject.tenant_id == auth.tenant_id,
        AcademicSubject.id.in_([str(x.subject_id) for x in body.items]),
        AcademicSubject.program_id == program.id,
        AcademicSubject.status == "active",
    ))).scalars().all()
    if len(subjects) != len(body.items):
        raise HTTPException(status_code=422, detail="Disciplinas devem ser ativas e do mesmo curso.")
    row = AcademicCurriculum(
        tenant_id=auth.tenant_id, program_id=program.id,
        code=body.code.strip(), label=body.label.strip(), created_by_user_id=auth.user_id,
    )
    db.add(row)
    await db.flush()
    for item in body.items:
        db.add(AcademicCurriculumItem(
            tenant_id=auth.tenant_id, curriculum_id=row.id,
            subject_id=str(item.subject_id), period_number=item.period_number,
            required=item.required,
            prerequisite_subject_id=str(item.prerequisite_subject_id) if item.prerequisite_subject_id else None,
        ))
    _event(db, auth.tenant_id, "staff", auth.user_id, "curriculum_created", "curriculum", row.id,
           {"items": len(body.items)})
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Currículo ou disciplinas duplicados.") from exc
    return {"id": row.id, "status": "draft", "items": len(body.items)}


@institution_router.post("/curricula/{curriculum_id}/publish")
async def publish_curriculum(
    curriculum_id: UUID,
    auth: AuthContext = Depends(require_permission("critical.manage")),
    db: AsyncSession = Depends(get_db),
):
    await _staff(db, auth)
    row = await _row(db, AcademicCurriculum, auth.tenant_id, curriculum_id, lock=True)
    if row.status != "draft":
        _conflict("Currículo já publicado.")
    items = (await db.execute(select(AcademicCurriculumItem).where(
        AcademicCurriculumItem.tenant_id == auth.tenant_id,
        AcademicCurriculumItem.curriculum_id == row.id,
    ))).scalars().all()
    try:
        validate_curriculum_graph([{
            "subject_id": x.subject_id, "period_number": x.period_number,
            "prerequisite_subject_id": x.prerequisite_subject_id,
        } for x in items])
    except AcademicRuleViolation as exc:
        _conflict(str(exc))
    row.status = "published"
    row.published_at = _now()
    _event(db, auth.tenant_id, "staff", auth.user_id, "curriculum_published", "curriculum", row.id,
           {"items": len(items)})
    await db.commit()
    return {"id": row.id, "status": "published"}


@institution_router.get("/curricula/{curriculum_id}")
async def curriculum_detail(
    curriculum_id: UUID,
    auth: AuthContext = Depends(require_permission("students.sensitive.view")),
    db: AsyncSession = Depends(get_db),
):
    await _staff(db, auth)
    row = await _row(db, AcademicCurriculum, auth.tenant_id, curriculum_id)
    items = (await db.execute(select(AcademicCurriculumItem).where(
        AcademicCurriculumItem.tenant_id == auth.tenant_id,
        AcademicCurriculumItem.curriculum_id == row.id,
    ).order_by(AcademicCurriculumItem.period_number))).scalars().all()
    return {"id": row.id, "code": row.code, "label": row.label,
            "program_id": row.program_id, "status": row.status,
            "items": [{"subject_id": x.subject_id, "period_number": x.period_number,
                       "required": x.required, "prerequisite_subject_id": x.prerequisite_subject_id}
                      for x in items]}


@institution_router.post("/programs/enroll", status_code=201)
async def admit_student(
    body: StudentProgramInput,
    auth: AuthContext = Depends(require_permission("students.edit")),
    db: AsyncSession = Depends(get_db),
):
    await _staff(db, auth)
    student = await _student(db, auth.tenant_id, str(body.student_id))
    program = await _row(db, AcademicProgram, auth.tenant_id, body.program_id)
    curriculum = await _row(db, AcademicCurriculum, auth.tenant_id, body.curriculum_id)
    if program.status != "active" or curriculum.status != "published" or curriculum.program_id != program.id:
        _conflict("Selecione um currículo publicado do curso ativo.")
    row = AcademicStudentProgram(
        tenant_id=auth.tenant_id, student_id=student.id,
        program_id=program.id, curriculum_id=curriculum.id,
    )
    db.add(row)
    try:
        await db.flush()
        _event(db, auth.tenant_id, "staff", auth.user_id, "admission_created", "student_program", row.id,
               {"program_id": program.id, "curriculum_id": curriculum.id})
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="O aluno já está vinculado a este curso.") from exc
    return {"id": row.id, "student_id": row.student_id, "program_id": row.program_id,
            "curriculum_id": row.curriculum_id, "status": row.status}


@institution_router.get("/students/{student_id}/programs")
async def student_programs(
    student_id: UUID,
    auth: AuthContext = Depends(require_permission("students.sensitive.view")),
    db: AsyncSession = Depends(get_db),
):
    await _staff(db, auth)
    await _student(db, auth.tenant_id, str(student_id))
    return await _programs(db, auth.tenant_id, str(student_id))


async def _programs(db: AsyncSession, tenant_id: str, student_id: str):
    rows = (await db.execute(select(AcademicStudentProgram, AcademicProgram.name, AcademicCurriculum.label)
        .join(AcademicProgram, and_(AcademicProgram.id == AcademicStudentProgram.program_id,
                                   AcademicProgram.tenant_id == AcademicStudentProgram.tenant_id))
        .join(AcademicCurriculum, and_(AcademicCurriculum.id == AcademicStudentProgram.curriculum_id,
                                       AcademicCurriculum.tenant_id == AcademicStudentProgram.tenant_id))
        .where(AcademicStudentProgram.tenant_id == tenant_id,
               AcademicStudentProgram.student_id == student_id)
        .order_by(AcademicStudentProgram.admitted_at.desc()).limit(30))).all()
    return {"items": [{
        "id": r.id, "student_id": r.student_id, "program_id": r.program_id,
        "program_name": name, "curriculum_id": r.curriculum_id,
        "curriculum_label": label, "status": r.status,
    } for r, name, label in rows]}


@portal_router.get("/programs")
async def portal_programs(
    identity: PortalIdentity = Depends(_portal_identity),
    db: AsyncSession = Depends(get_db),
):
    _enabled()
    return await _programs(db, identity.tenant_id, identity.student.id)


@institution_router.post("/classes/{class_id}/offer")
async def set_class_offering(
    class_id: UUID, body: OfferInput,
    auth: AuthContext = Depends(require_permission("critical.manage")),
    db: AsyncSession = Depends(get_db),
):
    await _staff(db, auth)
    row = await _row(db, AcademicClass, auth.tenant_id, class_id, lock=True)
    if row.status in CLOSED:
        _conflict("Oferta encerrada.")
    term = await _row(db, AcademicTerm, auth.tenant_id, row.term_id)
    subject = await _row(db, AcademicSubject, auth.tenant_id, row.subject_id)
    if body.enrollment_open and (term.ends_on < _now().date() or subject.status != "active"):
        _conflict("Oferta vencida ou disciplina inativa.")
    existing = (await db.execute(select(func.count()).select_from(AcademicClassEnrollment).where(
        AcademicClassEnrollment.tenant_id == auth.tenant_id,
        AcademicClassEnrollment.class_id == row.id,
        AcademicClassEnrollment.status.in_(("enrolled", "completed")),
    ))).scalar_one()
    if body.capacity is not None and body.capacity < existing:
        _conflict("A nova capacidade não pode ser inferior às matrículas existentes.")
    row.capacity = body.capacity
    row.enrollment_open = body.enrollment_open
    if body.enrollment_open:
        row.status = "active"
    _event(db, auth.tenant_id, "staff", auth.user_id, "class_offer_changed", "class", row.id,
           {"open": row.enrollment_open, "capacity": row.capacity})
    await db.commit()
    return {"id": row.id, "status": row.status, "enrollment_open": row.enrollment_open,
            "capacity": row.capacity, "occupied": existing}


async def _offers(db: AsyncSession, tenant_id: str, program: AcademicStudentProgram, term_id: str):
    curriculum = await _row(db, AcademicCurriculum, tenant_id, program.curriculum_id)
    if curriculum.status != "published":
        _conflict("Currículo não publicado.")
    query = (
        select(AcademicClass, AcademicSubject.name, AcademicCurriculumItem.period_number)
        .join(AcademicCurriculumItem, and_(
            AcademicCurriculumItem.tenant_id == AcademicClass.tenant_id,
            AcademicCurriculumItem.subject_id == AcademicClass.subject_id,
            AcademicCurriculumItem.curriculum_id == curriculum.id,
        ))
        .join(AcademicSubject, and_(
            AcademicSubject.tenant_id == AcademicClass.tenant_id,
            AcademicSubject.id == AcademicClass.subject_id,
        ))
        .where(AcademicClass.tenant_id == tenant_id,
               AcademicClass.term_id == term_id,
               AcademicClass.status == "active", AcademicClass.enrollment_open.is_(True))
        .order_by(AcademicSubject.name, AcademicClass.code).limit(200)
    )
    rows = (await db.execute(query)).all()
    items = []
    for row, name, number in rows:
        occupied = (await db.execute(select(func.count()).select_from(AcademicClassEnrollment).where(
            AcademicClassEnrollment.tenant_id == tenant_id,
            AcademicClassEnrollment.class_id == row.id,
            AcademicClassEnrollment.status.in_(("enrolled", "completed")),
        ))).scalar_one()
        items.append({
            "id": row.id, "code": row.code, "subject_id": row.subject_id,
            "subject_name": name, "period_number": number, "campus": row.campus,
            "capacity": row.capacity, "occupied": occupied,
            "available": row.capacity is None or occupied < row.capacity,
        })
    return {"items": items, "preview_limited": len(rows) == 200}


@institution_router.get("/programs/{student_program_id}/offers")
async def staff_offers(
    student_program_id: UUID, term_id: UUID,
    auth: AuthContext = Depends(require_permission("students.sensitive.view")),
    db: AsyncSession = Depends(get_db),
):
    await _staff(db, auth)
    program = await _row(db, AcademicStudentProgram, auth.tenant_id, student_program_id)
    await _row(db, AcademicTerm, auth.tenant_id, term_id)
    return await _offers(db, auth.tenant_id, program, str(term_id))


@portal_router.get("/programs/{student_program_id}/offers")
async def portal_offers(
    student_program_id: UUID, term_id: UUID,
    identity: PortalIdentity = Depends(_portal_identity),
    db: AsyncSession = Depends(get_db),
):
    _enabled()
    program = await _row(db, AcademicStudentProgram, identity.tenant_id, student_program_id)
    if program.student_id != identity.student.id:
        _missing()
    await _row(db, AcademicTerm, identity.tenant_id, term_id)
    return await _offers(db, identity.tenant_id, program, str(term_id))
