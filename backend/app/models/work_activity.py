"""Atividades operacionais da Central de Trabalho (distintas de InterventionLog)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# Status do trabalho operacional — não confundir com status de InterventionLog.
WORK_STATUSES = ("open", "in_progress", "completed", "cancelled")
WORK_ACTIVITY_TYPES = ("follow_up", "contact", "review", "other")
WORK_PRIORITIES = ("low", "normal", "high", "urgent")
WORK_ORIGINS = ("manual", "campaign")


class WorkActivity(Base):
    """Unidade de trabalho institucional atribuível a um membro do tenant.

    Não substitui InterventionLog: opcionalmente referencia um log de intervenção.
    """

    __tablename__ = "work_activities"
    __table_args__ = (
        CheckConstraint("priority IN ('low', 'normal', 'high', 'urgent')", name="ck_work_activities_priority"),
        CheckConstraint("origin_type IN ('manual', 'campaign')", name="ck_work_activities_origin_type"),
        Index("ix_work_activities_tenant_status", "tenant_id", "status"),
        Index("ix_work_activities_tenant_assignee", "tenant_id", "assignee_user_id"),
        Index("ix_work_activities_tenant_due", "tenant_id", "due_at"),
        Index("ix_work_activities_tenant_student", "tenant_id", "student_id"),
        Index("ix_work_activities_tenant_origin_status", "tenant_id", "origin_type", "status"),
        Index("ix_work_activities_tenant_priority_due", "tenant_id", "priority", "due_at"),
        Index(
            "uq_work_activities_tenant_source_key",
            "tenant_id",
            "source_key",
            unique=True,
            postgresql_where=text("source_key IS NOT NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    student_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False), ForeignKey("students.id", ondelete="SET NULL"), nullable=True
    )
    intervention_log_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False), ForeignKey("intervention_logs.id", ondelete="SET NULL"), nullable=True
    )

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    activity_type: Mapped[str] = mapped_column(String(40), nullable=False, default="follow_up")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="normal")
    origin_type: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")
    campaign_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False), ForeignKey("retention_campaigns.id", ondelete="SET NULL"), nullable=True
    )
    source_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    assignee_user_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False), ForeignKey("mira_users.id", ondelete="SET NULL"), nullable=True
    )
    created_by_user_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False), ForeignKey("mira_users.id", ondelete="SET NULL"), nullable=True
    )

    due_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class WorkActivityEvent(Base):
    """Histórico auditável de alterações em WorkActivity."""

    __tablename__ = "work_activity_events"
    __table_args__ = (
        Index("ix_work_activity_events_tenant_activity", "tenant_id", "activity_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    activity_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("work_activities.id", ondelete="CASCADE"), nullable=False
    )
    actor_user_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False), ForeignKey("mira_users.id", ondelete="SET NULL"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    payload: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
