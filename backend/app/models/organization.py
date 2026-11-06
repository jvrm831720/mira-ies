"""Organization legal entity, Membership and workspace-level branding.

Phase B of the product blueprint:
  User (global identity) → Membership (per workspace) → Tenant/Workspace (data boundary)
  Organization is the legal entity (CNPJ, country, operation profile).

During the dual-write period we keep User.tenant_id and User.role.
Membership becomes the source of truth for authorization once dual-write is complete.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Organization(Base):
    """Legal entity that may own one or more workspaces (1:1 in the first release)."""

    __tablename__ = "mira_organizations"
    __table_args__ = (
        UniqueConstraint("country_code", "tax_id_normalized", name="uq_mira_organizations_tax_id"),
        Index("ix_mira_organizations_tax_id", "tax_id_normalized"),
        Index("ix_mira_organizations_created", "created_at"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    # Legal / display
    legal_name: Mapped[str] = mapped_column(String(255), nullable=False)
    trade_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    country_code: Mapped[str] = mapped_column(String(2), nullable=False, default="BR")
    tax_id_normalized: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)  # CNPJ digits only
    tax_id_display: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)  # formatted
    # Operation profile chosen at onboarding: institution | billing | other
    operation_profile: Mapped[str] = mapped_column(String(32), nullable=False, default="institution")
    # Provenance of cadastral data
    tax_id_source: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # provider name or "manual"
    tax_id_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    address_snapshot: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    onboarding_profile: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class Membership(Base):
    """Link between a global User and a Tenant/Workspace.

    Replaces the single tenant_id + role that today live on User.
    During dual-write both are kept in sync.
    """

    __tablename__ = "mira_memberships"
    __table_args__ = (
        UniqueConstraint("user_id", "tenant_id", name="uq_mira_memberships_user_tenant"),
        UniqueConstraint("tenant_id", "id", name="uq_mira_memberships_tenant_id_id"),
        CheckConstraint(
            "status IN ('active', 'invited', 'suspended', 'left')",
            name="ck_mira_memberships_status",
        ),
        Index("ix_mira_memberships_user", "user_id"),
        Index("ix_mira_memberships_tenant_status", "tenant_id", "status"),
        ForeignKeyConstraint(
            ["tenant_id", "custom_role_id"],
            ["mira_tenant_roles.tenant_id", "mira_tenant_roles.id"],
            name="fk_mira_memberships_custom_role_tenant",
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("mira_users.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    # Role mirrors the legacy User.role values (admin, coordinator, viewer, ...)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="coordinator")
    custom_role_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), nullable=True)
    # active | invited | suspended | left
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    # How the membership was created
    origin: Mapped[str] = mapped_column(String(32), nullable=False, default="legacy_backfill")
    invited_by_user_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False), ForeignKey("mira_users.id", ondelete="SET NULL"), nullable=True
    )
    joined_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    left_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class TenantBranding(Base):
    """White-label branding for a workspace (portal do pagador / institutional)."""

    __tablename__ = "mira_tenant_branding"

    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True
    )
    logo_storage_key: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    primary_color: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    support_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    support_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    portal_title: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    extra: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class TenantDomain(Base):
    """Verified hostname that may be used for portal / SSO discovery."""

    __tablename__ = "mira_tenant_domains"
    __table_args__ = (
        UniqueConstraint("hostname", name="uq_mira_tenant_domains_hostname"),
        Index("ix_mira_tenant_domains_tenant", "tenant_id"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    hostname: Mapped[str] = mapped_column(String(255), nullable=False)
    # pending | verified | revoked
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    verification_token: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class ModuleEntitlement(Base):
    """Which product modules are enabled for a workspace (plan / feature flag)."""

    __tablename__ = "mira_module_entitlements"
    __table_args__ = (
        UniqueConstraint("tenant_id", "module_key", name="uq_mira_module_entitlements_tenant_module"),
        Index("ix_mira_module_entitlements_tenant", "tenant_id"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    # permanence | billing | data | workspace | mira_plan
    module_key: Mapped[str] = mapped_column(String(48), nullable=False)
    # enabled | disabled | trial
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="enabled")
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="default")  # plan | manual | trial
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
