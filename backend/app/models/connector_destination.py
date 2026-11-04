"""Tenant-scoped outbound connector destination approvals."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TenantConnectorDestination(Base):
    __tablename__ = "tenant_connector_destinations"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "connector_key", "hostname", "port",
            name="uq_tenant_connector_destination",
        ),
        CheckConstraint("scheme = 'https'", name="ck_tenant_connector_destination_scheme"),
        CheckConstraint("port = 443", name="ck_tenant_connector_destination_port"),
        Index("ix_tenant_connector_destinations_tenant_connector", "tenant_id", "connector_key", "is_enabled"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    connector_key: Mapped[str] = mapped_column(String(40), nullable=False)
    hostname: Mapped[str] = mapped_column(String(253), nullable=False)
    scheme: Mapped[str] = mapped_column(String(5), default="https", nullable=False)
    port: Mapped[int] = mapped_column(Integer, default=443, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    approval_reason: Mapped[str] = mapped_column(String(500), nullable=False)
    approved_by_user_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("mira_users.id", ondelete="SET NULL"), nullable=True)
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, onupdate=_utc_now, nullable=False)


class TenantConnectorDestinationAudit(Base):
    __tablename__ = "tenant_connector_destination_audit"
    __table_args__ = (
        CheckConstraint(
            "action IN ('approved', 'revoked')",
            name="ck_tenant_connector_destination_audit_action",
        ),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    destination_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    connector_key: Mapped[str] = mapped_column(String(40), nullable=False)
    hostname: Mapped[str] = mapped_column(String(253), nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    actor_user_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
