"""Wave 6 — native academic operations and versioned institutional rules.

Everything is tenant-scoped. Academic facts must be verified before being
published; unknown grades/attendance are never favorable defaults.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import (
    Boolean, CheckConstraint, Date, DateTime, ForeignKey,
    ForeignKeyConstraint, Index, Integer, Numeric, String, Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AcademicPolicy(Base):
    __tablename__ = "mira_academic_policies"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_mira_academic_policy_tenant_id"),
        UniqueConstraint("tenant_id", "version", name="uq_mira_academic_policy_version"),
        CheckConstraint("passing_percent BETWEEN 0 AND 100", name="ck_mira_academic_policy_grade"),
        CheckConstraint("min_attendance_percent BETWEEN 0 AND 100", name="ck_mira_academic_policy_attendance"),
        CheckConstraint("max_classes_per_term BETWEEN 1 AND 30", name="ck_mira_academic_policy_class_limit"),
        CheckConstraint("enrollment_closes_on IS NULL OR enrollment_opens_on IS NULL OR enrollment_closes_on >= enrollment_opens_on", name="ck_mira_academic_policy_window"),
    )
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    passing_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    min_attendance_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    max_classes_per_term: Mapped[int] = mapped_column(Integer, nullable=False)
    excused_excluded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    allow_reenrollment: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    enrollment_opens_on: Mapped[date | None] = mapped_column(Date)
    enrollment_closes_on: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    created_by_user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AcademicCurriculum(Base):
    __tablename__ = "mira_academic_curricula"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_mira_academic_curriculum_tenant_id"),
        UniqueConstraint("tenant_id", "program_id", "code", name="uq_mira_academic_curriculum_code"),
        ForeignKeyConstraint(["tenant_id", "program_id"], ["mira_academic_programs.tenant_id", "mira_academic_programs.id"], name="fk_mira_curriculum_program_tenant"),
    )
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False)
    program_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    label: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    created_by_user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AcademicCurriculumItem(Base):
    __tablename__ = "mira_academic_curriculum_items"
    __table_args__ = (
        UniqueConstraint("tenant_id", "curriculum_id", "subject_id", name="uq_mira_academic_curriculum_subject"),
        ForeignKeyConstraint(["tenant_id", "curriculum_id"], ["mira_academic_curricula.tenant_id", "mira_academic_curricula.id"], name="fk_mira_curriculum_item_curriculum_tenant"),
        ForeignKeyConstraint(["tenant_id", "subject_id"], ["mira_academic_subjects.tenant_id", "mira_academic_subjects.id"], name="fk_mira_curriculum_item_subject_tenant"),
        ForeignKeyConstraint(["tenant_id", "prerequisite_subject_id"], ["mira_academic_subjects.tenant_id", "mira_academic_subjects.id"], name="fk_mira_curriculum_item_prereq_tenant"),
        CheckConstraint("period_number BETWEEN 1 AND 30", name="ck_mira_curriculum_period"),
        CheckConstraint("prerequisite_subject_id IS NULL OR prerequisite_subject_id != subject_id", name="ck_mira_curriculum_not_self_prereq"),
    )
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False)
    curriculum_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    subject_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    period_number: Mapped[int] = mapped_column(Integer, nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    prerequisite_subject_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False))


class AcademicStudentProgram(Base):
    __tablename__ = "mira_academic_student_programs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_mira_student_program_tenant_id"),
        UniqueConstraint("tenant_id", "student_id", "program_id", name="uq_mira_student_program"),
        ForeignKeyConstraint(["tenant_id", "student_id"], ["students.tenant_id", "students.id"], name="fk_mira_student_program_student_tenant"),
        ForeignKeyConstraint(["tenant_id", "program_id"], ["mira_academic_programs.tenant_id", "mira_academic_programs.id"], name="fk_mira_student_program_program_tenant"),
        ForeignKeyConstraint(["tenant_id", "curriculum_id"], ["mira_academic_curricula.tenant_id", "mira_academic_curricula.id"], name="fk_mira_student_program_curriculum_tenant"),
        CheckConstraint("status IN ('active','suspended','completed','cancelled')", name="ck_mira_student_program_status"),
        Index("ix_mira_student_program_student", "tenant_id", "student_id"),
    )
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False)
    student_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    program_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    curriculum_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    admitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class AcademicEnrollmentRequest(Base):
    __tablename__ = "mira_academic_enrollment_requests"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_mira_enrollment_request_tenant_id"),
        UniqueConstraint("tenant_id", "student_program_id", "term_id", name="uq_mira_enrollment_request_student_term"),
        ForeignKeyConstraint(["tenant_id", "student_program_id"], ["mira_academic_student_programs.tenant_id", "mira_academic_student_programs.id"], name="fk_mira_enrollment_request_program_tenant"),
        ForeignKeyConstraint(["tenant_id", "term_id"], ["mira_academic_terms.tenant_id", "mira_academic_terms.id"], name="fk_mira_enrollment_request_term_tenant"),
        CheckConstraint("kind IN ('enrollment','reenrollment')", name="ck_mira_enrollment_request_kind"),
        CheckConstraint("status IN ('submitted','approved','rejected')", name="ck_mira_enrollment_request_status"),
        Index("ix_mira_enrollment_requests_queue", "tenant_id", "status", "submitted_at"),
    )
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False)
    student_program_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    term_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="submitted")
    requested_by: Mapped[str] = mapped_column(String(12), nullable=False)
    requested_by_user_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False))
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by_user_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False))
    decision_note: Mapped[str | None] = mapped_column(String(500))
    policy_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class AcademicEnrollmentRequestClass(Base):
    __tablename__ = "mira_academic_enrollment_request_classes"
    __table_args__ = (
        UniqueConstraint("tenant_id", "request_id", "class_id", name="uq_mira_enrollment_request_class"),
        ForeignKeyConstraint(["tenant_id", "request_id"], ["mira_academic_enrollment_requests.tenant_id", "mira_academic_enrollment_requests.id"], name="fk_mira_enrollment_req_class_request_tenant"),
        ForeignKeyConstraint(["tenant_id", "class_id"], ["mira_academic_classes.tenant_id", "mira_academic_classes.id"], name="fk_mira_enrollment_req_class_class_tenant"),
    )
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False)
    request_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    class_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)


class AcademicClassOutcome(Base):
    __tablename__ = "mira_academic_class_outcomes"
    __table_args__ = (
        UniqueConstraint("tenant_id", "class_id", "student_id", name="uq_mira_academic_class_outcome_student"),
        ForeignKeyConstraint(["tenant_id", "class_id"], ["mira_academic_classes.tenant_id", "mira_academic_classes.id"], name="fk_mira_outcome_class_tenant"),
        ForeignKeyConstraint(["tenant_id", "student_id"], ["students.tenant_id", "students.id"], name="fk_mira_outcome_student_tenant"),
        CheckConstraint("result IN ('passed','failed')", name="ck_mira_outcome_result"),
        CheckConstraint("score_percent BETWEEN 0 AND 100", name="ck_mira_outcome_score"),
        CheckConstraint("attendance_percent BETWEEN 0 AND 100", name="ck_mira_outcome_attendance"),
        Index("ix_mira_academic_outcome_student", "tenant_id", "student_id", "closed_at"),
    )
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False)
    class_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    student_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    score_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    attendance_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    result: Mapped[str] = mapped_column(String(12), nullable=False)
    policy_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    closed_by_user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    closed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class AcademicOperationEvent(Base):
    __tablename__ = "mira_academic_operation_events"
    __table_args__ = (
        Index("ix_mira_academic_op_events", "tenant_id", "target_kind", "target_id", "occurred_at"),
    )
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False)
    actor_kind: Mapped[str] = mapped_column(String(12), nullable=False)
    actor_user_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False))
    event_type: Mapped[str] = mapped_column(String(60), nullable=False)
    target_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    target_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
