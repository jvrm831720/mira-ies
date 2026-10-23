"""Eventos de engajamento observáveis para otimização de horário e risco dinâmico."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class StudentEngagementEvent(Base):
    __tablename__ = "student_engagement_events"
    __table_args__ = (
        UniqueConstraint("tenant_id", "event_key", name="uq_student_engagement_tenant_event_key"),
        Index("ix_student_engagement_tenant_student_time", "tenant_id", "student_id", "occurred_at"),
        Index("ix_student_engagement_tenant_type_time", "tenant_id", "event_type", "occurred_at"),
        Index("ix_student_engagement_intervention", "intervention_log_id"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    student_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("students.id", ondelete="CASCADE"), nullable=False
    )
    intervention_log_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("intervention_logs.id", ondelete="SET NULL"), nullable=True
    )
    event_key: Mapped[str] = mapped_column(String(200), nullable=False)
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    channel: Mapped[str | None] = mapped_column(String(20), nullable=True)
    source: Mapped[str] = mapped_column(String(40), nullable=False, default="system")
    provider: Mapped[str | None] = mapped_column(String(40), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    event_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
