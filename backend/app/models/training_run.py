"""Training runs and immutable dataset snapshots (Wave 13.3).

Snapshots capture the exact contribution hashes that fed a run. They are
append-only and never mutated. Actual model fitting remains out of scope here;
this layer records the governed execution boundary.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TrainingDatasetSnapshot(Base):
    __tablename__ = "training_dataset_snapshots"
    __table_args__ = (
        CheckConstraint(
            "scope IN ('shared_base', 'institutional')",
            name="ck_training_dataset_snapshots_scope",
        ),
        UniqueConstraint("dataset_hash", name="uq_training_dataset_snapshots_hash"),
        Index("ix_training_dataset_snapshots_scope_built", "scope", "built_at"),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    scope: Mapped[str] = mapped_column(String(20), nullable=False)
    dataset_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    # Ordered list of sanitized contribution content hashes included.
    contribution_hashes: Mapped[list] = mapped_column(JSONB, nullable=False)
    tenant_ids: Mapped[list] = mapped_column(JSONB, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    anonymization_rules_version: Mapped[str] = mapped_column(String(40), nullable=False)
    feature_schema_version: Mapped[str] = mapped_column(String(40), nullable=False)
    built_by_admin_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("mira_control_admins.id", ondelete="SET NULL"),
        nullable=True,
    )
    built_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class TrainingRun(Base):
    __tablename__ = "training_runs"
    __table_args__ = (
        CheckConstraint(
            "scope IN ('shared_base', 'institutional')",
            name="ck_training_runs_scope",
        ),
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')",
            name="ck_training_runs_status",
        ),
        UniqueConstraint("run_key", name="uq_training_runs_run_key"),
        Index("ix_training_runs_scope_status", "scope", "status"),
        Index("ix_training_runs_tenant_created", "tenant_id", "created_at"),
        Index("ix_training_runs_snapshot", "snapshot_id"),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    run_key: Mapped[str] = mapped_column(String(80), nullable=False)
    scope: Mapped[str] = mapped_column(String(20), nullable=False)
    tenant_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=True,
    )
    snapshot_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("training_dataset_snapshots.id", ondelete="RESTRICT"),
        nullable=False,
    )
    dataset_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    triggered_by_admin_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("mira_control_admins.id", ondelete="SET NULL"),
        nullable=True,
    )
    artifact_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("model_artifacts.id", ondelete="SET NULL"),
        nullable=True,
    )
    metrics: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
