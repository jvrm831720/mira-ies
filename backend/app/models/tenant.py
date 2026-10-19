"""
Multi-tenant + learning loop (Modelo Hibrido C).

- Tenant: isolamento por IES
- TrainingEvent: snapshot de features no momento do score + label posterior
- ModelArtifact: registry de modelos (base global vs tenant)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import (
    String,
    Integer,
    Float,
    DateTime,
    Text,
    ForeignKey,
    Index,
    Boolean,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.db.session import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    segment: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    active_model_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), nullable=True)
    labeled_events_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    positive_labels_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tenant_model_ready: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
    training_events: Mapped[list["TrainingEvent"]] = relationship(
        "TrainingEvent",
        back_populates="tenant",
        cascade="all, delete-orphan",
        foreign_keys="TrainingEvent.tenant_id",
    )


class ModelArtifact(Base):
    __tablename__ = "model_artifacts"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    tenant_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    version: Mapped[str] = mapped_column(String(40), nullable=False)
    scope: Mapped[str] = mapped_column(String(20), nullable=False, default="base")
    storage_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    metrics: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    feature_columns: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    trained_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class TrainingEvent(Base):
    __tablename__ = "training_events"
    __table_args__ = (
        Index("ix_training_events_tenant_labeled", "tenant_id", "label"),
        Index("ix_training_events_matricula", "tenant_id", "matricula"),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    student_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False), ForeignKey("students.id", ondelete="SET NULL"), nullable=True
    )
    batch_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False), ForeignKey("upload_batches.id", ondelete="SET NULL"), nullable=True
    )
    matricula: Mapped[str] = mapped_column(String(50), nullable=False)
    scored_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    features_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    model_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    adjusted_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    risk_level: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    model_version: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    model_scope: Mapped[str] = mapped_column(String(20), default="base", nullable=False)
    label: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    outcome: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    labeled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    outcome_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    tenant: Mapped["Tenant"] = relationship(
        "Tenant", back_populates="training_events", foreign_keys=[tenant_id]
    )
