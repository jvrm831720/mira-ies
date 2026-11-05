"""Student-owned schedule, academic calendar, attendance and published gradebook.

Every query derives identity from a validated, revocable student session.
No student_id, tenant_id or class list is trusted from query parameters.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.native_academic import PortalIdentity, _portal_identity
from app.core.config import get_settings
from app.db.session import get_db
from app.models.academic_catalog import (
    AcademicAssessment, AcademicAttendance, AcademicCalendarEvent,
    AcademicClass, AcademicClassEnrollment, AcademicGrade, AcademicLesson,
    AcademicSubject, AcademicTeacher, AcademicTerm,
)

router = APIRouter(prefix="/student-portal", tags=["Portal do Aluno — acadêmico"])


def _available() -> None:
    settings = get_settings()
    if not settings.student_portal_enabled or not settings.native_academic_catalog_enabled:
        raise HTTPException(status_code=503, detail="Dados acadêmicos ainda em homologação.")


def _range(first: date | None, last: date | None) -> tuple[datetime, datetime]:
    start = first or datetime.now(timezone.utc).date()
    end = last or (start + timedelta(days=30))
    if end < start or (end - start).days > 62:
        raise HTTPException(status_code=422, detail="Selecione no máximo 62 dias.")
    return (
        datetime.combine(start, time.min, tzinfo=timezone.utc),
        datetime.combine(end + timedelta(days=1), time.min, tzinfo=timezone.utc),
    )


def _visible_enrollments(identity: PortalIdentity):
    return select(AcademicClassEnrollment.class_id).where(
        AcademicClassEnrollment.tenant_id == identity.tenant_id,
        AcademicClassEnrollment.student_id == identity.student.id,
        AcademicClassEnrollment.status.in_(("enrolled", "completed")),
    )


@router.get("/schedule")
async def student_schedule(
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
    identity: PortalIdentity = Depends(_portal_identity),
    db: AsyncSession = Depends(get_db),
):
    _available()
    first, last = _range(start, end)
    lesson_rows = (await db.execute(
        select(AcademicLesson, AcademicSubject.name, AcademicTeacher.display_name)
        .join(AcademicClass, and_(
            AcademicClass.id == AcademicLesson.class_id,
            AcademicClass.tenant_id == AcademicLesson.tenant_id,
        ))
        .join(AcademicSubject, and_(
            AcademicSubject.id == AcademicClass.subject_id,
            AcademicSubject.tenant_id == AcademicClass.tenant_id,
        ))
        .outerjoin(AcademicTeacher, and_(
            AcademicTeacher.id == AcademicClass.teacher_id,
            AcademicTeacher.tenant_id == AcademicClass.tenant_id,
        ))
        .where(
            AcademicLesson.tenant_id == identity.tenant_id,
            AcademicLesson.publication_status == "published",
            AcademicLesson.class_id.in_(_visible_enrollments(identity)),
            AcademicLesson.starts_at >= first,
            AcademicLesson.starts_at < last,
        ).order_by(AcademicLesson.starts_at).limit(200)
    )).all()
    return {
        "timezone": "UTC",
        "range_start": first.isoformat(),
        "range_end_exclusive": last.isoformat(),
        "items": [{
            "id": row.id,
            "class_id": row.class_id,
            "subject": subject,
            "teacher_name": teacher,
            "starts_at": row.starts_at.isoformat(),
            "ends_at": row.ends_at.isoformat(),
            "topic": row.topic,
            "room": row.room,
        } for row, subject, teacher in lesson_rows],
        "limit": 200,
        "source": "mira_native_published_lessons",
    }


@router.get("/calendar")
async def student_calendar(
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
    identity: PortalIdentity = Depends(_portal_identity),
    db: AsyncSession = Depends(get_db),
):
    _available()
    first, last = _range(start, end)
    events = (await db.execute(
        select(AcademicCalendarEvent).where(
            AcademicCalendarEvent.tenant_id == identity.tenant_id,
            AcademicCalendarEvent.publication_status == "published",
            AcademicCalendarEvent.starts_at >= first,
            AcademicCalendarEvent.starts_at < last,
            or_(
                AcademicCalendarEvent.scope == "institution",
                and_(
                    AcademicCalendarEvent.scope == "class",
                    AcademicCalendarEvent.class_id.in_(_visible_enrollments(identity)),
                ),
            ),
        ).order_by(AcademicCalendarEvent.starts_at).limit(200)
    )).scalars().all()
    return {"items": [{
        "id": event.id,
        "scope": event.scope,
        "title": event.title,
        "starts_at": event.starts_at.isoformat(),
        "ends_at": event.ends_at.isoformat(),
        "location": event.location,
    } for event in events], "limit": 200, "timezone": "UTC"}


@router.get("/report-card")
async def student_report_card(
    term_id: UUID | None = Query(default=None),
    identity: PortalIdentity = Depends(_portal_identity),
    db: AsyncSession = Depends(get_db),
):
    _available()
    query = (
        select(
            AcademicGrade, AcademicAssessment.title, AcademicAssessment.max_score,
            AcademicSubject.name, AcademicTerm.code, AcademicTerm.label,
        )
        .join(AcademicAssessment, and_(
            AcademicAssessment.id == AcademicGrade.assessment_id,
            AcademicAssessment.class_id == AcademicGrade.class_id,
            AcademicAssessment.tenant_id == AcademicGrade.tenant_id,
        ))
        .join(AcademicClass, and_(
            AcademicClass.id == AcademicGrade.class_id,
            AcademicClass.tenant_id == AcademicGrade.tenant_id,
        ))
        .join(AcademicSubject, and_(
            AcademicSubject.id == AcademicClass.subject_id,
            AcademicSubject.tenant_id == AcademicClass.tenant_id,
        ))
        .join(AcademicTerm, and_(
            AcademicTerm.id == AcademicClass.term_id,
            AcademicTerm.tenant_id == AcademicClass.tenant_id,
        ))
        .where(
            AcademicGrade.tenant_id == identity.tenant_id,
            AcademicGrade.student_id == identity.student.id,
            AcademicGrade.class_id.in_(_visible_enrollments(identity)),
            AcademicGrade.publication_status == "published",
            AcademicAssessment.publication_status == "published",
        )
    )
    if term_id is not None:
        query = query.where(AcademicClass.term_id == str(term_id))
    rows = (await db.execute(
        query.order_by(AcademicGrade.graded_at.desc(), AcademicGrade.id.desc()).limit(300)
    )).all()
    return {
        "items": [{
            "assessment_id": grade.assessment_id,
            "class_id": grade.class_id,
            "subject": subject,
            "assessment": title,
            "score": str(grade.score),
            "max_score": str(max_score),
            "term_code": code,
            "term_label": label,
            "graded_at": grade.graded_at.isoformat(),
        } for grade, title, max_score, subject, code, label in rows],
        "limit": 300,
        "status": "published_records_only",
        "weighted_average": None,
        "note": "Somente avaliações publicadas. Média final não calculada sem regra institucional homologada.",
    }


@router.get("/attendance")
async def student_attendance(
    identity: PortalIdentity = Depends(_portal_identity),
    db: AsyncSession = Depends(get_db),
):
    _available()
    # Attendance is based ONLY on explicitly recorded and published lessons;
    # missing attendance rows never count as presence.
    rows = (await db.execute(
        select(AcademicSubject.name, AcademicClass.code,
               AcademicAttendance.status, func.count())
        .join(AcademicLesson, and_(
            AcademicLesson.id == AcademicAttendance.lesson_id,
            AcademicLesson.class_id == AcademicAttendance.class_id,
            AcademicLesson.tenant_id == AcademicAttendance.tenant_id,
        ))
        .join(AcademicClass, and_(
            AcademicClass.id == AcademicAttendance.class_id,
            AcademicClass.tenant_id == AcademicAttendance.tenant_id,
        ))
        .join(AcademicSubject, and_(
            AcademicSubject.id == AcademicClass.subject_id,
            AcademicSubject.tenant_id == AcademicClass.tenant_id,
        ))
        .where(
            AcademicAttendance.tenant_id == identity.tenant_id,
            AcademicAttendance.student_id == identity.student.id,
            AcademicAttendance.class_id.in_(_visible_enrollments(identity)),
            AcademicLesson.publication_status == "published",
        )
        .group_by(AcademicSubject.name, AcademicClass.code, AcademicAttendance.status)
        .order_by(AcademicSubject.name, AcademicClass.code)
        .limit(1000)
    )).all()
    result = {}
    for subject, class_code, status, number in rows:
        key = (subject, class_code)
        if key not in result:
            result[key] = {
                "subject": subject, "class_code": class_code,
                "present": 0, "absent": 0, "excused": 0, "unrecorded": 0,
            }
        if status in {"present", "absent", "excused", "unrecorded"}:
            result[key][status] = int(number)
    return {
        "items": list(result.values()),
        "rate": None,
        "status": "recorded_entries_only",
        "note": "Faltas não lançadas e aulas sem chamada permanecem desconhecidas; não se presume presença.",
    }
