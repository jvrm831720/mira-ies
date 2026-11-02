"""Contas Mira, convites de organização e desafios de autenticação."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "mira_users"
    __table_args__ = (
        UniqueConstraint("email", name="uq_mira_users_email"),
        UniqueConstraint("phone_e164", name="uq_mira_users_phone_e164"),
        Index("ix_mira_users_tenant_id", "tenant_id"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    phone_e164: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), default="coordinator", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    auth_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    mfa_totp_secret_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    mfa_enabled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    mfa_last_verified_step: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    mfa_failed_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    mfa_locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    onboarding_completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class OrganizationInvite(Base):
    """Convite pendente para entrar em um tenant (organização)."""

    __tablename__ = "mira_org_invites"
    __table_args__ = (
        Index("ix_mira_org_invites_tenant_status", "tenant_id", "status"),
        Index("ix_mira_org_invites_email", "email"),
        Index("ix_mira_org_invites_token_hash", "token_hash", unique=True),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="coordinator")
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    invited_by_user_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False), ForeignKey("mira_users.id", ondelete="SET NULL"), nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class AuthChallenge(Base):
    """Um OTP/reset token com expiração. Identificadores e tokens nunca ficam em texto puro."""

    __tablename__ = "mira_auth_challenges"
    __table_args__ = (
        Index("ix_mira_auth_challenges_lookup", "challenge_type", "identifier_hash", "created_at"),
        Index("ix_mira_auth_challenges_token_hash", "challenge_type", "token_hash"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False), ForeignKey("mira_users.id", ondelete="CASCADE"), nullable=True
    )
    challenge_type: Mapped[str] = mapped_column(String(32), nullable=False)
    identifier_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class MfaLoginChallenge(Base):
    """Desafio de segundo fator; o ticket é armazenado somente como hash."""
    __tablename__ = "mira_mfa_login_challenges"
    __table_args__ = (Index("ix_mira_mfa_login_challenges_user", "user_id", "created_at"),)

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("mira_users.id", ondelete="CASCADE"), nullable=False)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    ticket_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    purpose: Mapped[str] = mapped_column(String(16), default="verify", nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    consumed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class MfaRecoveryCode(Base):
    """Código de recuperação com hash individual e consumo único."""
    __tablename__ = "mira_mfa_recovery_codes"
    __table_args__ = (
        Index("ix_mira_mfa_recovery_codes_user", "user_id", "used_at"),
        Index("ix_mira_mfa_recovery_codes_tenant_id", "tenant_id"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("mira_users.id", ondelete="CASCADE"), nullable=False)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class MfaAuditEvent(Base):
    """Trilha de auditoria de segurança MFA, sempre vinculada ao tenant."""
    __tablename__ = "mira_mfa_audit_events"
    __table_args__ = (Index("ix_mira_mfa_audit_tenant_created", "tenant_id", "created_at"),)

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("mira_users.id", ondelete="SET NULL"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(48), nullable=False)
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class MfaTenantPolicy(Base):
    """Política MFA da instituição. O backend é a fonte de verdade."""
    __tablename__ = "mira_tenant_mfa_policies"

    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True
    )
    require_mfa_all: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    required_roles: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    updated_by_user_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False), ForeignKey("mira_users.id", ondelete="SET NULL"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class UserSession(Base):
    """Sessão autenticada revogável no servidor e associada a um único usuário/tenant."""
    __tablename__ = "mira_user_sessions"
    __table_args__ = (
        Index("ix_mira_user_sessions_user_active", "tenant_id", "user_id", "revoked_at"),
        Index("ix_mira_user_sessions_expiry", "expires_at"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("mira_users.id", ondelete="CASCADE"), nullable=False)
    aal: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    device_label: Mapped[str] = mapped_column(String(160), default="Dispositivo desconhecido", nullable=False)
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by_user_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("mira_users.id", ondelete="SET NULL"), nullable=True)
    revoke_reason: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
