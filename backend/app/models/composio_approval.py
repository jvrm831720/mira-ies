"""Tenant-scoped approval records for gated Composio tool execution."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TenantComposioToolApproval(Base):
    __tablename__ = "tenant_composio_tool_approvals"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "connected_account_id"],
            ["tenant_composio_accounts.tenant_id", "tenant_composio_accounts.connected_account_id"],
            name="fk_composio_approval_account_tenant",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "status IN ('pending_approval', 'approved', 'rejected', 'expired', 'cancelled', 'executing', 'succeeded', 'failed', 'unknown')",
            name="ck_composio_approval_status",
        ),
        CheckConstraint(
            "reviewed_by_user_id IS NULL OR reviewed_by_user_id <> requested_by_user_id",
            name="ck_composio_approval_four_eyes",
        ),
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_composio_approval_idempotency"),
        Index("ix_composio_approvals_tenant_status_expiry", "tenant_id", "status", "expires_at"),
        Index("ix_composio_approvals_account_status", "tenant_id", "connected_account_id", "status"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    connected_account_id: Mapped[str] = mapped_column(String(120), nullable=False)
    requested_by_user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("mira_users.id", ondelete="RESTRICT"), nullable=False)
    reviewed_by_user_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("mira_users.id", ondelete="RESTRICT"), nullable=True)
    toolkit_slug: Mapped[str] = mapped_column(String(80), nullable=False)
    tool_slug: Mapped[str] = mapped_column(String(120), nullable=False)
    tool_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    arguments_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="pending_approval", nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    execution_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
