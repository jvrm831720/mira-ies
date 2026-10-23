"""Trilha append-only de alterações nas preferências de comunicação."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ConsentAuditEvent(Base):
    """Evento de alteração de preferência; snapshots pequenos, sem conteúdo de mensagem."""

    __tablename__ = "consent_audit_events"
    __table_args__ = (
        Index("ix_consent_audit_tenant_student_time", "tenant_id", "student_id", "occurred_at"),
        Index("ix_consent_audit_tenant_time", "tenant_id", "occurred_at"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    student_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False), ForeignKey("students.id", ondelete="SET NULL"), nullable=True, index=True
    )
    student_matricula: Mapped[str] = mapped_column(String(50), nullable=False)
    event_type: Mapped[str] = mapped_column(String(60), nullable=False)
    channel: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    topic: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    previous_value: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    new_value: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    method: Mapped[str] = mapped_column(String(60), nullable=False)
    location: Mapped[str] = mapped_column(String(120), nullable=False)
    source_reference: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    actor_user_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
