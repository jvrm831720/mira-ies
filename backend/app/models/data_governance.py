"""Governance records for the two MIRA model-training modalities.

A policy row is historical evidence, not a client-controlled runtime flag.
Shared training must fail closed unless a current, approved policy and evidence
are both present.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TenantDataUsePolicy(Base):
    __tablename__ = "tenant_data_use_policies"
    __table_args__ = (
        CheckConstraint(
            "mode IN ('shared_training', 'institution_only')",
            name="ck_tenant_data_use_policy_mode",
        ),
        CheckConstraint(
            "expires_at IS NULL OR expires_at > effective_at",
            name="ck_tenant_data_use_policy_expiry",
        ),
        Index(
            "ix_tenant_data_use_policy_tenant_effective",
            "tenant_id",
            "effective_at",
        ),
        Index(
            "ix_tenant_data_use_policy_tenant_revoked",
            "tenant_id",
            "revoked_at",
        ),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    contract_reference: Mapped[str] = mapped_column(String(160), nullable=False)
    contract_version: Mapped[str] = mapped_column(String(80), nullable=False)
    effective_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    approved_by_admin_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("mira_control_admins.id", ondelete="SET NULL"),
        nullable=True,
    )
    evidence_reference: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
