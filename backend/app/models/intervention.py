"""Logs do sistema multiagente de retencao (orquestrador + canais WhatsApp/E-mail/SMS)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import String, Float, Date, Integer, DateTime, Text, ForeignKey, Index, UniqueConstraint, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.db.session import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class InterventionLog(Base):
    """Evento de retenção: decisão + execução + desfecho.

    Ciclo:
    1) decision_reason explica por que a ação foi escolhida ou pulada
    2) status/delivery_status acompanham o envio
    3) outcome fecha o loop para aprendizado (permaneceu, evadiu, respondeu…)
    """

    __tablename__ = "intervention_logs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_intervention_logs_tenant_idempotency_key"),
        Index("ix_intervention_logs_tenant_student_channel", "tenant_id", "student_id", "channel", "created_at"),
        Index("ix_intervention_logs_tenant_status", "tenant_id", "status"),
        Index("ix_intervention_logs_tenant_external_id", "tenant_id", "external_id"),
        Index("ix_intervention_logs_tenant_outcome", "tenant_id", "outcome"),
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

    # Motivo auditável da decisão (ex.: "risk_level=critico; channel=whatsapp; anti_spam=ok")
    decision_reason: Mapped[Optional[str]] = mapped_column(String(240), nullable=True)
    # Snapshot leve das features no momento da decisão (score, opt_out, canais disponíveis)
    decision_context: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    provider: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    external_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)

    correlation_id: Mapped[Optional[str]] = mapped_column(String(160), nullable=True, index=True)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    job_id: Mapped[Optional[str]] = mapped_column(String(80), nullable=True, index=True)
    campaign_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, index=True)

    delivery_status: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    delivery_event_id: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    delivery_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Desfecho posterior (learning loop)
    # null | responded | no_response | stayed | dropped | transferred | unknown
    outcome: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    outcome_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    outcome_source: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)  # manual|import|system
    outcome_note: Mapped[Optional[str]] = mapped_column(String(240), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

class InterventionLogDailyAggregate(Base):
    """Aggregated intervention statistics without student identifiers."""

    __tablename__ = "intervention_log_daily_aggregates"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "metric_date",
            "status",
            "channel_bucket",
            "risk_level_bucket",
            "outcome_bucket",
            name="uq_intervention_log_daily_aggregate_key",
        ),
        Index("ix_intervention_aggregate_tenant_date", "tenant_id", "metric_date"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    metric_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    channel_bucket: Mapped[str] = mapped_column(String(20), nullable=False, default="_none")
    risk_level_bucket: Mapped[str] = mapped_column(String(20), nullable=False, default="_none")
    outcome_bucket: Mapped[str] = mapped_column(String(40), nullable=False, default="_none")
    event_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    aggregated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
