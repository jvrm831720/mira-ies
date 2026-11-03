"""Tenant-scoped persistence for TOTVS RM snapshot synchronization."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, ForeignKeyConstraint, Integer, String,
    Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RmSyncScope(Base):
    __tablename__ = "rm_sync_scopes"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "coligada_id", "source_name", "entity_name", "schema_version",
            name="uq_rm_sync_scopes_identity",
        ),
        UniqueConstraint("id", "tenant_id", name="uq_rm_sync_scopes_id_tenant"),
        ForeignKeyConstraint(
            ["current_snapshot_run_id", "tenant_id"],
            ["rm_sync_runs.id", "rm_sync_runs.tenant_id"],
            name="fk_rm_sync_scopes_current_run_tenant",
            deferrable=True,
            initially="DEFERRED",
        ),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    coligada_id: Mapped[str] = mapped_column(String(80), nullable=False)
    source_name: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_name: Mapped[str] = mapped_column(String(120), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(40), nullable=False)
    current_snapshot_run_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, onupdate=_utc_now, nullable=False)


class RmSyncRun(Base):
    __tablename__ = "rm_sync_runs"
    __table_args__ = (
        UniqueConstraint("id", "tenant_id", name="uq_rm_sync_runs_id_tenant"),
        ForeignKeyConstraint(
            ["scope_id", "tenant_id"], ["rm_sync_scopes.id", "rm_sync_scopes.tenant_id"],
            ondelete="CASCADE", name="fk_rm_sync_runs_scope_tenant",
        ),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    scope_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    identity_fields: Mapped[list] = mapped_column(JSONB, nullable=False)
    coligada_field: Mapped[str] = mapped_column(String(80), nullable=False)
    deletion_semantics_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="staging", nullable=False)
    next_offset: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    record_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    source_complete: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    expected_record_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    diff: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class RmSyncPage(Base):
    __tablename__ = "rm_sync_pages"
    __table_args__ = (
        UniqueConstraint("run_id", "offset", name="uq_rm_sync_pages_run_offset"),
        ForeignKeyConstraint(
            ["run_id", "tenant_id"], ["rm_sync_runs.id", "rm_sync_runs.tenant_id"],
            ondelete="CASCADE", name="fk_rm_sync_pages_run_tenant",
        ),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    run_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    offset: Mapped[int] = mapped_column(Integer, nullable=False)
    next_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    record_count: Mapped[int] = mapped_column(Integer, nullable=False)
    has_more: Mapped[bool] = mapped_column(Boolean, nullable=False)
    records: Mapped[list] = mapped_column(JSONB, nullable=False)


class RmSyncRecord(Base):
    __tablename__ = "rm_sync_records"
    __table_args__ = (
        UniqueConstraint("run_id", "identity_key", name="uq_rm_sync_records_run_identity"),
        ForeignKeyConstraint(
            ["run_id", "tenant_id"], ["rm_sync_runs.id", "rm_sync_runs.tenant_id"],
            ondelete="CASCADE", name="fk_rm_sync_records_run_tenant",
        ),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    run_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    identity_key: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
