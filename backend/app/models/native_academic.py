"""Native MIRA Education records and a completely separate student portal identity.

This is an original PostgreSQL/FastAPI implementation mapping the product
concepts of Frappe Education; it does not run Frappe or copy its source code.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, ForeignKeyConstraint, Index,
    Numeric, String, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MiraAcademicRecord(Base):
    """Student-scoped enrolment/attendance/assessment/fee record from a named source."""

    __tablename__ = "mira_academic_records"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "student_id"], ["students.tenant_id", "students.id"],
            name="fk_mira_academic_student_tenant", ondelete="CASCADE",
        ),
        UniqueConstraint(
            "tenant_id", "student_id", "kind", "source", "source_record_id",
            name="uq_mira_academic_source_record",
        ),
        Index("ix_mira_academic_student_kind", "tenant_id", "student_id", "kind"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    student_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    source: Mapped[str] = mapped_column(String(60), nullable=False)
    source_record_id: Mapped[str] = mapped_column(String(120), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    academic_period: Mapped[str | None] = mapped_column(String(60))
    status: Mapped[str | None] = mapped_column(String(60))
    event_date: Mapped[date | None] = mapped_column(Date)
    grade: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    max_grade: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    due_date: Mapped[date | None] = mapped_column(Date)
    currency: Mapped[str | None] = mapped_column(String(3))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class MiraStudentPortalInvite(Base):
    __tablename__ = "mira_student_portal_invites"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "student_id"], ["students.tenant_id", "students.id"],
            name="fk_mira_portal_invite_student_tenant", ondelete="CASCADE",
        ),
        Index("ix_mira_portal_invites_tenant_student", "tenant_id", "student_id"),
        UniqueConstraint("token_hash", name="uq_mira_portal_invite_token_hash"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    student_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    issued_by_user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("mira_users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class MiraStudentPortalSession(Base):
    __tablename__ = "mira_student_portal_sessions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "student_id"], ["students.tenant_id", "students.id"],
            name="fk_mira_portal_session_student_tenant", ondelete="CASCADE",
        ),
        UniqueConstraint("token_hash", name="uq_mira_portal_session_token_hash"),
        Index("ix_mira_portal_sessions_student", "tenant_id", "student_id", "revoked_at"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    student_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
