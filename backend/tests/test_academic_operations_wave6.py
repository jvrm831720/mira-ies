"""Wave 6: deterministic academic rules and tenant-aware real PostgreSQL lifecycle."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select, text

from app.api.academic_operations import (
    AttendanceBatch, AttendanceEntry, CurriculumInput, CurriculumItemInput,
    DecisionInput, EnrollmentInput, GradeBatch, GradeEntry, OfferInput,
    PolicyInput, StudentProgramInput, _enabled, admit_student, close_class,
    closing_preview, create_curriculum, create_policy, decide_enrollment,
    portal_enrollment_requests, portal_request_enrollment, portal_transcript,
    publish_class_grades, publish_curriculum, publish_policy,
    record_attendance, record_grades, set_class_offering, staff_request_enrollment,
)
from app.core.config import get_settings
from app.models.academic_catalog import (
    AcademicAssessment, AcademicClass, AcademicClassEnrollment, AcademicLesson,
    AcademicProgram, AcademicSubject, AcademicTerm,
)
from app.models.academic_operations import (
    AcademicClassOutcome, AcademicOperationEvent, AcademicPolicy,
)
from app.models.auth import User
from app.models.student import Student, UploadBatch
from app.services.academic_operations import (
    AcademicRuleViolation, calculate_result, policy_snapshot, validate_curriculum_graph,
)


def test_wave6_rules_reject_cycles_and_missing_prerequisites():
    one, two = str(uuid4()), str(uuid4())
    validate_curriculum_graph([
        {"subject_id": one, "period_number": 1, "prerequisite_subject_id": None},
        {"subject_id": two, "period_number": 2, "prerequisite_subject_id": one},
    ])
    with pytest.raises(AcademicRuleViolation):
        validate_curriculum_graph([
            {"subject_id": one, "period_number": 1, "prerequisite_subject_id": two},
            {"subject_id": two, "period_number": 1, "prerequisite_subject_id": one},
        ])
    with pytest.raises(AcademicRuleViolation):
        validate_curriculum_graph([
            {"subject_id": one, "period_number": 1, "prerequisite_subject_id": str(uuid4())},
        ])
    with pytest.raises(AcademicRuleViolation):
        validate_curriculum_graph([
            {"subject_id": one, "period_number": 1},
            {"subject_id": one, "period_number": 2},
        ])


def test_wave6_outcome_is_fail_closed_and_uses_explicit_policy():
    data = [(Decimal("7"), Decimal("10"), True)]
    rules = {"passing_percent": Decimal("60"), "min_attendance_percent": Decimal("75"),
             "excused_excluded": True}
    assert calculate_result(data, [None], **rules)["ready"] is False
    assert calculate_result(data, ["unrecorded"], **rules)["ready"] is False
    assert calculate_result([(Decimal("0"), Decimal("10"), False)], ["present"], **rules)["ready"] is False
    assert calculate_result(data, ["excused"], **rules)["ready"] is False
    passed = calculate_result(data, ["present", "present", "absent", "excused"], **rules)
    assert passed["ready"] and passed["result"] == "failed"  # 2/3 = 66.67% < 75%
    assert passed["attendance_percent"] == "66.67"
    passed = calculate_result(data, ["present", "present", "present", "excused"], **rules)
    assert passed["ready"] and passed["result"] == "passed"
    assert passed["attendance_percent"] == "100.00"
    assert calculate_result([(Decimal("12"), Decimal("10"), True)], ["present"], **rules)["ready"] is False


def test_wave6_inputs_are_typed_and_gate_is_off_by_default(monkeypatch):
    with pytest.raises(ValidationError):
        PolicyInput(passing_percent=101, min_attendance_percent=75, max_classes_per_term=8)
    with pytest.raises(ValidationError):
        PolicyInput(passing_percent=60, min_attendance_percent=75, max_classes_per_term=8,
                    enrollment_opens_on=date(2028, 3, 10),
                    enrollment_closes_on=date(2028, 3, 1))
    with pytest.raises(ValidationError):
        GradeBatch(assessment_id=uuid4(), entries=[GradeEntry(student_id=uuid4(), score=-1)])
    with pytest.raises(ValidationError):
        AttendanceEntry(student_id=uuid4(), status="auto_present")
    monkeypatch.setattr(get_settings(), "native_academic_operations_enabled", False)
    with pytest.raises(HTTPException) as disabled:
        _enabled()
    assert disabled.value.status_code == 503


async def _seed(db, tenant_factory, slug):
    t, _ = await tenant_factory(slug=slug)
    t.segment = "higher_education"
    db.add(t)
    await db.commit()
    await db.execute(text("SELECT set_config('app.tenant_id', :id, true)"), {"id": t.id})
    user = User(tenant_id=t.id, display_name="Coordenação", email=slug + "@example.test",
                role="admin", password_hash="not-a-real-hash", mfa_enabled_at=datetime.now(timezone.utc))
    batch = UploadBatch(tenant_id=t.id, filename="academic.csv", original_filename="academic.csv")
    program = AcademicProgram(tenant_id=t.id, code="ENG", name="Engenharia", status="active")
    term = AcademicTerm(tenant_id=t.id, code="2027-1", label="2027.1",
                        starts_on=date.today(), ends_on=date.today()+timedelta(days=180),
                        status="planned")
    term2 = AcademicTerm(tenant_id=t.id, code="2027-2", label="2027.2",
                         starts_on=date.today()+timedelta(days=181),
                         ends_on=date.today()+timedelta(days=360),
                         status="planned")
    db.add_all([user, batch, program, term, term2])
    await db.flush()
    student = Student(tenant_id=t.id, batch_id=batch.id, matricula="MAT-" + slug, nome="Aluno A")
    other_student = Student(tenant_id=t.id, batch_id=batch.id,
                            matricula="MAT-B-" + slug, nome="Aluno B")
    sub_a = AcademicSubject(tenant_id=t.id, program_id=program.id,
                            code="CALC", name="Cálculo", status="active")
    sub_b = AcademicSubject(tenant_id=t.id, program_id=program.id,
                            code="ALG", name="Álgebra Avançada", status="active")
    db.add_all([student, other_student, sub_a, sub_b])
    await db.flush()
    cls_a = AcademicClass(tenant_id=t.id, subject_id=sub_a.id, term_id=term.id,
                          code="CALC-01", status="active", capacity=1, enrollment_open=True)
    cls_b = AcademicClass(tenant_id=t.id, subject_id=sub_b.id, term_id=term2.id,
                          code="ALG-01", status="active", capacity=3, enrollment_open=True)
    db.add_all([cls_a, cls_b])
    await db.commit()
    auth = SimpleNamespace(tenant=t, tenant_id=t.id, user_id=user.id,
                           session_id=str(uuid4()), aal=2, role="admin")
    portal = SimpleNamespace(tenant_id=t.id, student=student)
    other_portal = SimpleNamespace(tenant_id=t.id, student=other_student)
    return t, auth, portal, other_portal, program, term, term2, sub_a, sub_b, cls_a, cls_b


@pytest.mark.asyncio
async def test_wave6_full_enrollment_grade_attendance_transcript_and_prerequisite(
    db_session, tenant_factory, monkeypatch,
):
    settings = get_settings()
    for name in ("native_academic_enabled", "native_academic_catalog_enabled",
                 "native_academic_operations_enabled"):
        monkeypatch.setattr(settings, name, True)
    t, auth, portal, other_portal, program, term, term2, sub_a, sub_b, cls_a, cls_b = await _seed(
        db_session, tenant_factory, "wave6-lifecycle",
    )
    await db_session.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": t.id})
    policy = await create_policy(PolicyInput(
        passing_percent=60, min_attendance_percent=75,
        max_classes_per_term=6,
    ), auth=auth, db=db_session)
    await publish_policy(UUID(policy["id"]), auth=auth, db=db_session)
    curr = await create_curriculum(CurriculumInput(
        program_id=UUID(program.id), code="M1", label="Matriz 1",
        items=[
            CurriculumItemInput(subject_id=UUID(sub_a.id), period_number=1),
            CurriculumItemInput(subject_id=UUID(sub_b.id), period_number=2,
                                prerequisite_subject_id=UUID(sub_a.id)),
        ],
    ), auth=auth, db=db_session)
    await publish_curriculum(UUID(curr["id"]), auth=auth, db=db_session)
    admitted = await admit_student(StudentProgramInput(
        student_id=UUID(portal.student.id), program_id=UUID(program.id),
        curriculum_id=UUID(curr["id"]),
    ), auth=auth, db=db_session)
    second = await admit_student(StudentProgramInput(
        student_id=UUID(other_portal.student.id), program_id=UUID(program.id),
        curriculum_id=UUID(curr["id"]),
    ), auth=auth, db=db_session)
    payload = EnrollmentInput(
        student_program_id=UUID(admitted["id"]), term_id=UUID(term.id),
        class_ids=[UUID(cls_a.id)],
    )
    portal_action = SimpleNamespace(headers={"x-mira-portal-action": "1"})
    request = await portal_request_enrollment(
        payload, portal_action, identity=portal, db=db_session,
    )
    assert request["status"] == "submitted"
    assert request["kind"] == "enrollment"
    with pytest.raises(HTTPException) as replay:
        await portal_request_enrollment(payload, portal_action, identity=portal, db=db_session)
    assert replay.value.status_code == 409
    with pytest.raises(HTTPException) as cross_student:
        await portal_request_enrollment(payload, portal_action, identity=other_portal, db=db_session)
    assert cross_student.value.status_code == 404
    decision = await decide_enrollment(UUID(request["id"]), DecisionInput(
        approve=True, note="Documentos conferidos e vaga validada.",
    ), auth=auth, db=db_session)
    assert decision["status"] == "approved"
    assert (await db_session.execute(select(AcademicClassEnrollment).where(
        AcademicClassEnrollment.tenant_id == t.id,
        AcademicClassEnrollment.student_id == portal.student.id,
        AcademicClassEnrollment.class_id == cls_a.id,
    ))).scalar_one().status == "enrolled"
    # Capacity remains enforced at request time for the second student.
    with pytest.raises(HTTPException) as capacity:
        await staff_request_enrollment(EnrollmentInput(
            student_program_id=UUID(second["id"]), term_id=UUID(term.id),
            class_ids=[UUID(cls_a.id)],
        ), auth=auth, db=db_session)
    assert capacity.value.status_code == 409
    # A prerequisite cannot be bypassed for the second-term offer.
    with pytest.raises(HTTPException) as prerequisite:
        await portal_request_enrollment(EnrollmentInput(
            student_program_id=UUID(admitted["id"]), term_id=UUID(term2.id),
            class_ids=[UUID(cls_b.id)],
        ), portal_action, identity=portal, db=db_session)
    assert prerequisite.value.status_code == 409
    exam = AcademicAssessment(tenant_id=t.id, class_id=cls_a.id, code="EX1",
                              title="Prova 1", max_score=Decimal("10"),
                              publication_status="published")
    lesson = AcademicLesson(tenant_id=t.id, class_id=cls_a.id,
                            starts_at=datetime.now(timezone.utc),
                            ends_at=datetime.now(timezone.utc)+timedelta(hours=2),
                            publication_status="published")
    db_session.add_all([exam, lesson])
    await db_session.commit()
    await db_session.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": t.id})
    incomplete = await closing_preview(UUID(cls_a.id), auth=auth, db=db_session)
    assert not incomplete["ready"]
    await record_grades(UUID(cls_a.id), GradeBatch(
        assessment_id=UUID(exam.id), entries=[
            GradeEntry(student_id=UUID(portal.student.id), score=Decimal("8")),
        ],
    ), auth=auth, db=db_session)
    incomplete = await closing_preview(UUID(cls_a.id), auth=auth, db=db_session)
    assert not incomplete["ready"]
    await publish_class_grades(UUID(cls_a.id), body=SimpleNamespace(assessment_id=UUID(exam.id)),
                               auth=auth, db=db_session)
    await record_attendance(UUID(cls_a.id), AttendanceBatch(
        lesson_id=UUID(lesson.id), entries=[
            AttendanceEntry(student_id=UUID(portal.student.id), status="present"),
        ],
    ), auth=auth, db=db_session)
    complete = await closing_preview(UUID(cls_a.id), auth=auth, db=db_session)
    assert complete["ready"]
    assert complete["items"][0]["result"] == "passed"
    closed = await close_class(UUID(cls_a.id), auth=auth, db=db_session)
    assert closed["outcomes"] == 1
    transcript = await portal_transcript(identity=portal, db=db_session)
    assert len(transcript["items"]) == 1
    assert transcript["items"][0]["result"] == "passed"
    assert transcript["items"][0]["policy_version"] == 1
    assert transcript["official_document"] is False
    with pytest.raises(HTTPException):
        await close_class(UUID(cls_a.id), auth=auth, db=db_session)
    assert (await db_session.execute(select(AcademicClassOutcome).where(
        AcademicClassOutcome.tenant_id == t.id,
    ))).scalars().all()
    # The prerequisite is satisfied after finalized approval.
    reenroll = await portal_request_enrollment(EnrollmentInput(
        student_program_id=UUID(admitted["id"]), term_id=UUID(term2.id),
        class_ids=[UUID(cls_b.id)],
    ), portal_action, identity=portal, db=db_session)
    assert reenroll["kind"] == "reenrollment"


@pytest.mark.asyncio
async def test_wave6_cross_tenant_decision_is_hidden(db_session, tenant_factory, monkeypatch):
    for name in ("native_academic_enabled", "native_academic_catalog_enabled",
                 "native_academic_operations_enabled"):
        monkeypatch.setattr(get_settings(), name, True)
    a = await _seed(db_session, tenant_factory, "wave6-isolation-a")
    b = await _seed(db_session, tenant_factory, "wave6-isolation-b")
    await db_session.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": a[0].id})
    with pytest.raises(HTTPException) as hidden:
        await set_class_offering(UUID(b[9].id), OfferInput(capacity=1, enrollment_open=True),
                                 auth=a[1], db=db_session)
    assert hidden.value.status_code == 404
    # No unknown policy or secret default is used.
    with pytest.raises(HTTPException) as missing:
        await admit_student(StudentProgramInput(
            student_id=UUID(b[2].student.id), program_id=UUID(a[4].id),
            curriculum_id=UUID(uuid4()),
        ), auth=a[1], db=db_session)
    assert missing.value.status_code == 404


def test_wave6_policy_snapshot_is_numeric_and_minimal():
    p = SimpleNamespace(version=7, passing_percent=Decimal("60"), min_attendance_percent=Decimal("75"),
                        max_classes_per_term=8, excused_excluded=True, allow_reenrollment=False,
                        enrollment_opens_on=None, enrollment_closes_on=date(2030, 12, 1))
    assert policy_snapshot(p) == {
        "version": 7, "passing_percent": "60", "min_attendance_percent": "75",
        "max_classes_per_term": 8, "excused_excluded": True, "allow_reenrollment": False,
        "enrollment_opens_on": None, "enrollment_closes_on": "2030-12-01",
    }
