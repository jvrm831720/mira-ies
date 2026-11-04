"""Confirmed academic outcomes used to measure student permanence over time."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AcademicOutcome(Base):
    """Institution-reported enrollment outcome with source and term provenance."""

    __tablename__ = "academic_outcomes"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "source",
            "source_record_id",
            name="uq_academic_outcomes_tenant_source_record",
        ),
        Index("ix_academic_outcomes_tenant_period", "tenant_id", "academic_period"),
        Index("ix_academic_outcomes_tenant_observed", "tenant_id", "observed_at"),
        Index("ix_academic_outcomes_tenant_matricula", "tenant_id", "matricula"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    student_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("students.id", ondelete="SET NULL"), nullable=True
    )
    matricula: Mapped[str] = mapped_column(String(50), nullable=False)
    course: Mapped[str | None] = mapped_column(String(150), nullable=True)
    academic_period: Mapped[str | None] = mapped_column(String(40), nullable=True)
    outcome: Mapped[str] = mapped_column(String(40), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str] = mapped_column(String(80), nullable=False, default="manual")
    source_record_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
