"""Logs do sistema multiagente de retencao (orquestrador + canais WhatsApp/E-mail/SMS)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import String, Float, DateTime, Text, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.db.session import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class InterventionLog(Base):
    __tablename__ = "intervention_logs"
    __table_args__ = (
        Index("ix_intervention_logs_tenant_student_channel", "tenant_id", "student_id", "channel", "created_at"),
        Index("ix_intervention_logs_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    student_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False), ForeignKey("students.id", ondelete="SET NULL"), nullable=True
    )
    matricula: Mapped[str] = mapped_column(String(50), nullable=False)

    # None quando nenhum canal era viavel (ex: sem telefone/email) ou risco baixo
    channel: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    risk_level: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    risk_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    template_id: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    # Preview truncado da mensagem — nunca o corpo completo (evita log de PII desnecessario)
    message_preview: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)

    status: Mapped[str] = mapped_column(String(20), nullable=False)  # planned|sent|dry_run|failed|skipped
    skip_reason: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    provider: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    external_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
