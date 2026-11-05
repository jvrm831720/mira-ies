"""Tenant-scoped metadata for future Composio sessions, accounts and tool audit.

OAuth credentials are intentionally never stored in MIRA. Composio remains the
credential custodian; this module stores only opaque references and audit metadata.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TenantComposioSession(Base):
    __tablename__ = "tenant_composio_sessions"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_tenant_composio_sessions_tenant"),
        UniqueConstraint("composio_user_id", name="uq_tenant_composio_sessions_user"),
        CheckConstraint("status IN ('provisioned', 'active', 'disabled')", name="ck_tenant_composio_sessions_status"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    composio_user_id: Mapped[str] = mapped_column(String(80), nullable=False)
    session_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="provisioned", nullable=False)
    created_by_user_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("mira_users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, onupdate=_utc_now, nullable=False)


class TenantComposioAccount(Base):
    __tablename__ = "tenant_composio_accounts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "toolkit_slug", "connected_account_id", name="uq_tenant_composio_account"),
        CheckConstraint("status IN ('active', 'expired', 'revoked', 'error')", name="ck_tenant_composio_accounts_status"),
        Index("ix_tenant_composio_accounts_tenant_toolkit", "tenant_id", "toolkit_slug", "status"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    toolkit_slug: Mapped[str] = mapped_column(String(80), nullable=False)
    connected_account_id: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    auth_config_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    account_metadata: Mapped[dict] = mapped_column("metadata", JSONB, default=dict, nullable=False)
    connected_by_user_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("mira_users.id", ondelete="SET NULL"), nullable=True)
    connected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    disconnected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, onupdate=_utc_now, nullable=False)


class TenantComposioToolAudit(Base):
    """Append-only metadata about tool calls; never stores raw inputs or outputs."""

    __tablename__ = "tenant_composio_tool_audit"
    __table_args__ = (
        CheckConstraint("status IN ('requested', 'succeeded', 'failed', 'denied', 'pending_approval')", name="ck_tenant_composio_tool_audit_status"),
        Index("ix_tenant_composio_tool_audit_tenant_created", "tenant_id", "created_at"),
        Index("ix_tenant_composio_tool_audit_execution", "execution_id"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    actor_user_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("mira_users.id", ondelete="SET NULL"), nullable=True)
    connected_account_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    toolkit_slug: Mapped[str] = mapped_column(String(80), nullable=False)
    tool_slug: Mapped[str] = mapped_column(String(120), nullable=False)
    execution_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    approval_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    approval_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    request_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)


class TenantComposioToolkitPolicy(Base):
    """Institution-owned exposure policy for one toolkit and its selected tools."""

    __tablename__ = "tenant_composio_toolkit_policies"
    __table_args__ = (
        UniqueConstraint("tenant_id", "toolkit_slug", name="uq_tenant_composio_toolkit_policy"),
        CheckConstraint("toolkit_slug ~ '^[a-z0-9][a-z0-9_-]*$'", name="ck_composio_toolkit_slug"),
        CheckConstraint("NOT is_enabled OR jsonb_array_length(tool_slugs) > 0", name="ck_composio_enabled_requires_tools"),
        Index("ix_tenant_composio_toolkit_policies_enabled", "tenant_id", "is_enabled"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    toolkit_slug: Mapped[str] = mapped_column(String(80), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    tool_slugs: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    updated_by_user_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("mira_users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, onupdate=_utc_now, nullable=False)
