"""Canonical feature observations from integrations (native connectors or Composio).

This layer is the data-source contract for the predictive model. Tool execution
(Composio actions) is separate: only explicit data-source policies may write
observations that feed scoring, signals and training.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TenantIntegrationDataSource(Base):
    """Per-tenant policy: which integration may ingest features for the model."""

    __tablename__ = "tenant_integration_data_sources"
    __table_args__ = (
        UniqueConstraint("tenant_id", "source_kind", "source_key", name="uq_tenant_integration_data_source"),
        CheckConstraint(
            "source_kind IN ('native_connector', 'composio', 'upload', 'system')",
            name="ck_integration_data_source_kind",
        ),
        CheckConstraint(
            "source_key ~ '^[a-z0-9][a-z0-9_.-]{0,79}$'",
            name="ck_integration_data_source_key",
        ),
        Index("ix_tenant_integration_data_sources_enabled", "tenant_id", "is_enabled"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    source_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    source_key: Mapped[str] = mapped_column(String(80), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    feature_keys: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    updated_by_user_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("mira_users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, onupdate=_utc_now, nullable=False
    )


class StudentFeatureObservation(Base):
    """Idempotent feature observation written by an authorized integration source."""

    __tablename__ = "student_feature_observations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "observation_key", name="uq_student_feature_observation_key"),
        CheckConstraint(
            "source_kind IN ('native_connector', 'composio', 'upload', 'system')",
            name="ck_feature_observation_source_kind",
        ),
        CheckConstraint(
            "feature_key ~ '^[a-z][a-z0-9_]{1,63}$'",
            name="ck_feature_observation_feature_key",
        ),
        CheckConstraint(
            "value_type IN ('number', 'text', 'boolean', 'categorical')",
            name="ck_feature_observation_value_type",
        ),
        Index("ix_feature_obs_tenant_student_feature", "tenant_id", "student_id", "feature_key"),
        Index("ix_feature_obs_tenant_source_time", "tenant_id", "source_kind", "source_key", "observed_at"),
        Index("ix_feature_obs_tenant_feature_time", "tenant_id", "feature_key", "observed_at"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    student_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("students.id", ondelete="CASCADE"), nullable=True
    )
    subject_ref: Mapped[str | None] = mapped_column(String(160), nullable=True)
    observation_key: Mapped[str] = mapped_column(String(200), nullable=False)
    source_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    source_key: Mapped[str] = mapped_column(String(80), nullable=False)
    feature_key: Mapped[str] = mapped_column(String(64), nullable=False)
    value_type: Mapped[str] = mapped_column(String(16), nullable=False)
    value_number: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_text: Mapped[str | None] = mapped_column(String(500), nullable=True)
    value_boolean: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    reliability: Mapped[str] = mapped_column(String(20), default="partial", nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
