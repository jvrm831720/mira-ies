"""Wave 2: academic publication boundaries, portal scopes, native catalog shapes.

Integration paths require disposable PostgreSQL and are never run against production.
"""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import text

from app.api.academic_catalog import (
    AssessmentInput, CalendarInput, CatalogBatch, LessonInput, TermInput, list_catalog_records,
)
from app.api.academic_portal import _range, student_calendar, student_report_card, student_schedule
from app.api.native_academic import PortalIdentity
from app.core.auth import AuthContext
from app.core.config import get_settings
from app.models.academic_catalog import (
    AcademicAssessment, AcademicCalendarEvent, AcademicClass,
    AcademicClassEnrollment, AcademicGrade, AcademicLesson,
    AcademicProgram, AcademicSubject, AcademicTerm,
)
from app.models.native_academic import MiraStudentPortalSession
from app.models.student import Student, UploadBatch


def test_model_prevents_invalid_dates_and_scores():
    now = datetime.now(timezone.utc)
    with pytest.raises(ValidationError):
        TermInput(code="wrong", label="Período inválido",
                  starts_on=date(2026, 11, 8), ends_on=date(2026, 11, 5))
    with pytest.raises(ValidationError):
        LessonInput(class_id=uuid4(), starts_at=now, ends_at=now)
    with pytest.raises(ValidationError):
        AssessmentInput(class_id=uuid4(), code="n1", title="Nota", max_score=Decimal("-2"))
    with pytest.raises(ValidationError):
        CalendarInput(term_id=uuid4(), scope="institution",
                      class_id=uuid4(), title="Evento",
                      starts_at=now, ends_at=now+timedelta(hours=1))
    with pytest.raises(ValidationError):
        CatalogBatch()  # disallow no-op imports


def test_calendar_query_limits_ranges():
    start, end = _range(date(2026, 11, 5), date(2026, 11, 15))
    assert start.date() == date(2026, 11, 5)
    assert end.date() == date(2026, 11, 16)
    with pytest.raises(HTTPException) as exc:
        _range(date(2026, 1, 1), date(2026, 7, 1))
    assert exc.value.status_code == 422


async def _setup_ies(db, tenant, *, suffix: str):
    await db.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": tenant.id})
    tenant.segment = "higher_education"
    upload = UploadBatch(tenant_id=tenant.id, filename=f"{suffix}.csv", original_filename=f"{suffix}.csv")
    db.add(upload)
    await db.flush()
    student = Student(tenant_id=tenant.id, batch_id=upload.id,
                      matricula=f"M-{suffix}", nome=f"Aluno {suffix}")
    db.add(student)
    await db.flush()

    program = AcademicProgram(tenant_id=tenant.id, code=f"P-{suffix}", name=f"Curso {suffix}")
    db.add(program)
    await db.flush()
    subject = AcademicSubject(tenant_id=tenant.id, program_id=program.id,
                              code=f"S-{suffix}", name=f"Disciplina {suffix}")
    term = AcademicTerm(tenant_id=tenant.id, code=f"T-{suffix}", label=f"Semestre {suffix}",
                        starts_on=date(2026, 1, 1), ends_on=date(2026, 12, 31))
    db.add_all([subject, term])
    await db.flush()
    clazz = AcademicClass(tenant_id=tenant.id, subject_id=subject.id,
                          term_id=term.id, code=f"C-{suffix}", status="active")
    db.add(clazz)
    await db.flush()
    db.add(AcademicClassEnrollment(tenant_id=tenant.id, class_id=clazz.id,
                                   student_id=student.id, enrolled_on=date(2026, 1, 1)))
    now = datetime(2026, 11, 6, 13, tzinfo=timezone.utc)
    lesson = AcademicLesson(tenant_id=tenant.id, class_id=clazz.id, starts_at=now,
                            ends_at=now+timedelta(hours=1), topic="Aula publicada",
                            publication_status="published")
    assessment = AcademicAssessment(tenant_id=tenant.id, class_id=clazz.id, code="EX-1",
                                    title="Exame final", max_score=Decimal("10"),
                                    publication_status="published")
    db.add_all([lesson, assessment])
    await db.flush()
    db.add(AcademicGrade(tenant_id=tenant.id, class_id=clazz.id,
                         assessment_id=assessment.id, student_id=student.id,
                         score=Decimal("8.50"), publication_status="published"))
    db.add(AcademicCalendarEvent(
        tenant_id=tenant.id, term_id=term.id, class_id=clazz.id,
        scope="class", title=f"Evento {suffix}", starts_at=now,
        ends_at=now+timedelta(hours=1), publication_status="published",
    ))
    await db.commit()
    return student


async def test_student_portal_only_sees_own_published_classes(
    tenant_factory, db_session, monkeypatch,
):
    monkeypatch.setattr(get_settings(), "native_academic_catalog_enabled", True)
    monkeypatch.setattr(get_settings(), "student_portal_enabled", True)
    a, _ = await tenant_factory(slug="course-ies-a")
    b, _ = await tenant_factory(slug="course-ies-b")
    student_a = await _setup_ies(db_session, a, suffix="a")
    student_b = await _setup_ies(db_session, b, suffix="b")
    await db_session.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": a.id})
    session = MiraStudentPortalSession(
        tenant_id=a.id, student_id=student_a.id,
        token_hash="0"*64,
        expires_at=datetime.now(timezone.utc)+timedelta(hours=8),
    )
    db_session.add(session)
    await db_session.flush()
    identity = PortalIdentity(tenant_id=a.id, tenant=a, student=student_a, session=session)
    schedule = await student_schedule(date(2026, 11, 5), date(2026, 11, 10), identity, db_session)
    calendar = await student_calendar(date(2026, 11, 5), date(2026, 11, 10), identity, db_session)
    grades = await student_report_card(None, identity, db_session)
    assert len(schedule["items"]) == 1
    assert schedule["items"][0]["subject"] == "Disciplina a"
    assert len(calendar["items"]) == 1
    assert calendar["items"][0]["title"] == "Evento a"
    assert len(grades["items"]) == 1
    assert grades["items"][0]["score"] == "8.50"
    assert "Disciplina b" not in str(schedule)
    assert "Evento b" not in str(calendar)
    assert student_b.id not in str(grades)


async def test_unpublished_records_never_reach_portal(
    tenant_factory, db_session, monkeypatch,
):
    monkeypatch.setattr(get_settings(), "native_academic_catalog_enabled", True)
    monkeypatch.setattr(get_settings(), "student_portal_enabled", True)
    tenant, _ = await tenant_factory(slug="course-ies-unpublished")
    student = await _setup_ies(db_session, tenant, suffix="drafts")
    await db_session.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": tenant.id})
    session = MiraStudentPortalSession(
        tenant_id=tenant.id, student_id=student.id, token_hash="1"*64,
        expires_at=datetime.now(timezone.utc)+timedelta(hours=8),
    )
    db_session.add(session)
    lessons = (await db_session.execute(
        __import__("sqlalchemy").select(AcademicLesson).where(AcademicLesson.tenant_id == tenant.id)
    )).scalars().all()
    assessments = (await db_session.execute(
        __import__("sqlalchemy").select(AcademicAssessment).where(AcademicAssessment.tenant_id == tenant.id)
    )).scalars().all()
    events = (await db_session.execute(
        __import__("sqlalchemy").select(AcademicCalendarEvent).where(AcademicCalendarEvent.tenant_id == tenant.id)
    )).scalars().all()
    for row in [*lessons, *assessments, *events]:
        row.publication_status = "draft"
    await db_session.flush()
    identity = PortalIdentity(tenant_id=tenant.id, tenant=tenant, student=student, session=session)
    schedule = await student_schedule(date(2026, 11, 5), date(2026, 11, 10), identity, db_session)
    calendar = await student_calendar(date(2026, 11, 5), date(2026, 11, 10), identity, db_session)
    grades = await student_report_card(None, identity, db_session)
    assert schedule["items"] == []
    assert calendar["items"] == []
    assert grades["items"] == []


async def test_catalog_pages_filter_and_isolate_tenants(tenant_factory, db_session, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "native_academic_enabled", True)
    monkeypatch.setattr(settings, "native_academic_catalog_enabled", True)
    a, _ = await tenant_factory(slug="catalog-page-a")
    b, _ = await tenant_factory(slug="catalog-page-b")
    await _setup_ies(db_session, a, suffix="p1")
    await _setup_ies(db_session, a, suffix="p2")
    await _setup_ies(db_session, b, suffix="private")
    await db_session.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": a.id})
    auth = AuthContext(
        tenant=a, tenant_id=a.id, tenant_slug=a.slug,
        user_id=str(uuid4()), session_id=str(uuid4()),
    )

    async def page(query, offset=0):
        return await list_catalog_records(
            "programs", q=query, program_id=None, status=None, sort="code", desc=True, offset=offset,
            limit=1, auth=auth, db=db_session,
        )

    first = await page("curso")
    second = await page("curso", offset=1)
    assert [row["code"] for row in first["items"]] == ["P-p2"]
    assert first["has_more"] is True
    assert [row["code"] for row in second["items"]] == ["P-p1"]
    assert second["has_more"] is False
    assert (await page("private"))["items"] == []
    assert (await page("%"))["items"] == []
