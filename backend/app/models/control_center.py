"""Identidades e trilha de auditoria exclusivas do MIRA Control Center."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AdminPrincipal(Base):
    __tablename__ = "mira_control_admins"
    __table_args__ = (
        UniqueConstraint("email", name="uq_mira_control_admins_email"),
        Index("ix_mira_control_admins_active", "is_active"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="support")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    auth_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class AdminEmailChallenge(Base):
    __tablename__ = "mira_control_admin_challenges"
    __table_args__ = (
        Index("ix_mira_control_admin_challenge_lookup", "email_hash", "created_at"),
        Index("ix_mira_control_admin_challenge_expiry", "expires_at"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    admin_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("mira_control_admins.id", ondelete="CASCADE"), nullable=False)
    email_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class AdminAuditEvent(Base):
    __tablename__ = "mira_control_admin_audit"
    __table_args__ = (
        Index("ix_mira_control_admin_audit_created", "created_at"),
        Index("ix_mira_control_admin_audit_actor", "actor_admin_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    actor_admin_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("mira_control_admins.id", ondelete="SET NULL"), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    result: Mapped[str] = mapped_column(String(32), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    metadata_redacted: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)



class AdminBillingRecord(Base):
    """Registro manual de plano e vencimento por instituição."""

    __tablename__ = "mira_control_billing_records"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_mira_control_billing_tenant"),
        Index("ix_mira_control_billing_due", "payment_status", "due_at"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    created_by_admin_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("mira_control_admins.id", ondelete="SET NULL"), nullable=True
    )
    plan_name: Mapped[str] = mapped_column(String(120), nullable=False)
    plan_price_brl: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    billing_cycle: Mapped[str] = mapped_column(String(16), nullable=False, default="monthly")
    payment_link: Mapped[str | None] = mapped_column(String(500), nullable=True)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    plan_status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    payment_status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)
