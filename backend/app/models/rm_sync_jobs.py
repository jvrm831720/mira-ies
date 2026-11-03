"""Durable tenant-scoped queue for TOTVS RM snapshot orchestration."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RmSyncJob(Base):
    __tablename__ = "rm_sync_jobs"
    __table_args__ = (
        UniqueConstraint("id", "tenant_id", name="uq_rm_sync_jobs_id_tenant"),
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_rm_sync_jobs_tenant_idempotency"),
        ForeignKeyConstraint(
            ["scope_id", "tenant_id"], ["rm_sync_scopes.id", "rm_sync_scopes.tenant_id"],
            ondelete="CASCADE", name="fk_rm_sync_jobs_scope_tenant",
        ),
        ForeignKeyConstraint(
            ["snapshot_run_id", "tenant_id"], ["rm_sync_runs.id", "rm_sync_runs.tenant_id"],
            name="fk_rm_sync_jobs_snapshot_tenant",
        ),
        Index("ix_rm_sync_jobs_queue", "status", "available_at", "created_at"),
        Index("ix_rm_sync_jobs_tenant_created", "tenant_id", "created_at"),
        Index("ix_rm_sync_jobs_scope_status", "scope_id", "status"),
        Index(
            "uq_rm_sync_jobs_active_coligada", "tenant_id", "coligada_id", unique=True,
            postgresql_where=text("status IN ('queued', 'running', 'retry_wait', 'cancel_requested', 'publishing')"),
        ),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    scope_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    coligada_id: Mapped[str] = mapped_column(String(80), nullable=False)
    snapshot_run_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    request: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="queued")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)
    worker_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RmSyncJobEvent(Base):
    __tablename__ = "rm_sync_job_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["job_id", "tenant_id"], ["rm_sync_jobs.id", "rm_sync_jobs.tenant_id"],
            ondelete="CASCADE", name="fk_rm_sync_job_events_job_tenant",
        ),
        Index("ix_rm_sync_job_events_tenant_job", "tenant_id", "job_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    job_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    event_type: Mapped[str] = mapped_column(String(60), nullable=False)
    severity: Mapped[str] = mapped_column(String(12), nullable=False, default="info")
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)
