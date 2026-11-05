"""MIRA Education native course catalog, class sessions, attendance and report cards.

Original domain implementation inspired by education product concepts,
without importing Frappe runtime, ERPNext code, or a second database.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint, Date, DateTime, ForeignKey,
    ForeignKeyConstraint, Index, Integer, Numeric, String, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class AcademicProgram(Base):
    __tablename__ = "mira_academic_programs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_mira_program_tenant_id"),
        UniqueConstraint("tenant_id", "code", name="uq_mira_program_code"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    modality: Mapped[str | None] = mapped_column(String(48))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc)


class AcademicSubject(Base):
    __tablename__ = "mira_academic_subjects"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_mira_subject_tenant_id"),
        UniqueConstraint("tenant_id", "program_id", "code", name="uq_mira_subject_program_code"),
        ForeignKeyConstraint(["tenant_id", "program_id"], ["mira_academic_programs.tenant_id", "mira_academic_programs.id"],
                             name="fk_mira_subject_program_tenant", ondelete="CASCADE"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    program_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    credit_hours: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")


class AcademicTeacher(Base):
    __tablename__ = "mira_academic_teachers"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_mira_teacher_tenant_id"),
        UniqueConstraint("tenant_id", "staff_code", name="uq_mira_teacher_staff_code"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    staff_code: Mapped[str] = mapped_column(String(60), nullable=False)
    display_name: Mapped[str] = mapped_column(String(180), nullable=False)
    department: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")


class AcademicTerm(Base):
    __tablename__ = "mira_academic_terms"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_mira_term_tenant_id"),
        UniqueConstraint("tenant_id", "code", name="uq_mira_term_code"),
        CheckConstraint("ends_on >= starts_on", name="ck_mira_term_dates"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    ends_on: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="planned")


class AcademicClass(Base):
    __tablename__ = "mira_academic_classes"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_mira_class_tenant_id"),
        UniqueConstraint("tenant_id", "code", "term_id", name="uq_mira_class_code_term"),
        ForeignKeyConstraint(["tenant_id", "subject_id"], ["mira_academic_subjects.tenant_id", "mira_academic_subjects.id"],
                             name="fk_mira_class_subject_tenant", ondelete="RESTRICT"),
        ForeignKeyConstraint(["tenant_id", "term_id"], ["mira_academic_terms.tenant_id", "mira_academic_terms.id"],
                             name="fk_mira_class_term_tenant", ondelete="RESTRICT"),
        ForeignKeyConstraint(["tenant_id", "teacher_id"], ["mira_academic_teachers.tenant_id", "mira_academic_teachers.id"],
                             name="fk_mira_class_teacher_tenant", ondelete="RESTRICT"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    subject_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    term_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    teacher_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False))
    code: Mapped[str] = mapped_column(String(60), nullable=False)
    campus: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="planned")


class AcademicClassEnrollment(Base):
    __tablename__ = "mira_academic_class_enrollments"
    __table_args__ = (
        UniqueConstraint("tenant_id", "class_id", "student_id", name="uq_mira_class_enrollment"),
        ForeignKeyConstraint(["tenant_id", "class_id"], ["mira_academic_classes.tenant_id", "mira_academic_classes.id"],
                             name="fk_mira_enrollment_class_tenant", ondelete="CASCADE"),
        ForeignKeyConstraint(["tenant_id", "student_id"], ["students.tenant_id", "students.id"],
                             name="fk_mira_enrollment_student_tenant", ondelete="CASCADE"),
        Index("ix_mira_enrollment_student", "tenant_id", "student_id"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    class_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    student_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="enrolled")
    enrolled_on: Mapped[date] = mapped_column(Date, nullable=False)


class AcademicLesson(Base):
    __tablename__ = "mira_academic_lessons"
    __table_args__ = (
        UniqueConstraint("tenant_id", "class_id", "id", name="uq_mira_lesson_tenant_class_id"),
        UniqueConstraint("tenant_id", "class_id", "starts_at", name="uq_mira_lesson_class_start"),
        ForeignKeyConstraint(["tenant_id", "class_id"], ["mira_academic_classes.tenant_id", "mira_academic_classes.id"],
                             name="fk_mira_lesson_class_tenant", ondelete="CASCADE"),
        CheckConstraint("ends_at > starts_at", name="ck_mira_lesson_duration"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    class_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    topic: Mapped[str | None] = mapped_column(String(200))
    room: Mapped[str | None] = mapped_column(String(120))
    publication_status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")


class AcademicAttendance(Base):
    __tablename__ = "mira_academic_attendance"
    __table_args__ = (
        UniqueConstraint("tenant_id", "lesson_id", "student_id", name="uq_mira_attendance_lesson_student"),
        ForeignKeyConstraint(["tenant_id", "class_id", "lesson_id"],
                             ["mira_academic_lessons.tenant_id", "mira_academic_lessons.class_id", "mira_academic_lessons.id"],
                             name="fk_mira_attendance_lesson_tenant_class", ondelete="CASCADE"),
        ForeignKeyConstraint(["tenant_id", "class_id", "student_id"],
                             ["mira_academic_class_enrollments.tenant_id", "mira_academic_class_enrollments.class_id",
                              "mira_academic_class_enrollments.student_id"],
                             name="fk_mira_attendance_enrollment_tenant_class", ondelete="CASCADE"),
        CheckConstraint("status IN ('present','absent','excused','unrecorded')", name="ck_mira_attendance_status"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    class_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    lesson_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    student_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="unrecorded")
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc)


class AcademicAssessment(Base):
    __tablename__ = "mira_academic_assessments"
    __table_args__ = (
        UniqueConstraint("tenant_id", "class_id", "id", name="uq_mira_assessment_tenant_class_id"),
        UniqueConstraint("tenant_id", "class_id", "code", name="uq_mira_assessment_code"),
        ForeignKeyConstraint(["tenant_id", "class_id"], ["mira_academic_classes.tenant_id", "mira_academic_classes.id"],
                             name="fk_mira_assessment_class_tenant", ondelete="CASCADE"),
        CheckConstraint("max_score > 0", name="ck_mira_assessment_max_score"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    class_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    max_score: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    publication_status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")


class AcademicGrade(Base):
    __tablename__ = "mira_academic_grades"
    __table_args__ = (
        UniqueConstraint("tenant_id", "assessment_id", "student_id", name="uq_mira_grade_assessment_student"),
        ForeignKeyConstraint(["tenant_id", "class_id", "assessment_id"],
                             ["mira_academic_assessments.tenant_id", "mira_academic_assessments.class_id",
                              "mira_academic_assessments.id"],
                             name="fk_mira_grade_assessment_tenant_class", ondelete="CASCADE"),
        ForeignKeyConstraint(["tenant_id", "class_id", "student_id"],
                             ["mira_academic_class_enrollments.tenant_id", "mira_academic_class_enrollments.class_id",
                              "mira_academic_class_enrollments.student_id"],
                             name="fk_mira_grade_enrollment_tenant_class", ondelete="CASCADE"),
        CheckConstraint("score >= 0", name="ck_mira_grade_nonnegative"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    class_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    assessment_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    student_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    score: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    publication_status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    graded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc)


class AcademicCalendarEvent(Base):
    __tablename__ = "mira_academic_calendar_events"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "term_id"], ["mira_academic_terms.tenant_id", "mira_academic_terms.id"],
                             name="fk_mira_calendar_term_tenant", ondelete="CASCADE"),
        ForeignKeyConstraint(["tenant_id", "class_id"], ["mira_academic_classes.tenant_id", "mira_academic_classes.id"],
                             name="fk_mira_calendar_class_tenant", ondelete="CASCADE"),
        CheckConstraint("ends_at > starts_at", name="ck_mira_calendar_duration"),
        CheckConstraint("(scope = 'institution' AND class_id IS NULL) OR (scope = 'class' AND class_id IS NOT NULL)",
                        name="ck_mira_calendar_scope"),
        Index("ix_mira_calendar_tenant_time", "tenant_id", "starts_at"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    term_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    class_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False))
    scope: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    location: Mapped[str | None] = mapped_column(String(120))
    publication_status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
