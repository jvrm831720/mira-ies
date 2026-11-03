"""Durable, tenant-isolated SophiA synchronization jobs and latest resource snapshots."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SophiaSyncJob(Base):
    __tablename__ = "sophia_sync_jobs"
    __table_args__ = (
        UniqueConstraint("id", "tenant_id", name="uq_sophia_sync_jobs_id_tenant"),
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_sophia_sync_jobs_idempotency"),
        Index("ix_sophia_sync_jobs_queue", "status", "available_at", "created_at"),
        Index("ix_sophia_sync_jobs_tenant_created", "tenant_id", "created_at"),
        Index(
            "uq_sophia_sync_jobs_one_active_per_tenant", "tenant_id", unique=True,
            postgresql_where=text("status IN ('queued', 'running', 'retry_wait')"),
        ),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    request: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="queued")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=4)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)
    worker_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SophiaSyncJobEvent(Base):
    __tablename__ = "sophia_sync_job_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["job_id", "tenant_id"], ["sophia_sync_jobs.id", "sophia_sync_jobs.tenant_id"],
            ondelete="CASCADE", name="fk_sophia_sync_events_job_tenant",
        ),
        Index("ix_sophia_sync_events_tenant_job", "tenant_id", "job_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    job_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    event_type: Mapped[str] = mapped_column(String(60), nullable=False)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)


class SophiaStudentResource(Base):
    """Latest source payload per linked student/resource; raw source values are preserved."""
    __tablename__ = "sophia_student_resources"
    __table_args__ = (
        UniqueConstraint("tenant_id", "student_id", "resource", "job_id", name="uq_sophia_resource_student_job"),
        ForeignKeyConstraint(
            ["tenant_id", "student_id"], ["students.tenant_id", "students.id"],
            ondelete="CASCADE", name="fk_sophia_resource_student_tenant",
        ),
        ForeignKeyConstraint(
            ["job_id", "tenant_id"], ["sophia_sync_jobs.id", "sophia_sync_jobs.tenant_id"],
            ondelete="CASCADE", name="fk_sophia_resource_job_tenant",
        ),
        Index("ix_sophia_resources_tenant_resource", "tenant_id", "resource"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    student_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    job_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    resource: Mapped[str] = mapped_column(String(40), nullable=False)
    source_codigo_interno: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[list] = mapped_column(JSONB, nullable=False)
    record_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)
