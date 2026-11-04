"""Persistent registry of contributions evaluated for shared MIRA Base training.

No personal student identifiers are stored. Only sanitized hashes, policy
references, and eligibility decisions live here.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class EligibleContribution(Base):
    __tablename__ = "eligible_contributions"
    __table_args__ = (
        CheckConstraint(
            "modality IN ('shared_training', 'institution_only')",
            name="ck_eligible_contributions_modality",
        ),
        CheckConstraint(
            "eligibility_status IN ('eligible', 'rejected', 'revoked')",
            name="ck_eligible_contributions_status",
        ),
        UniqueConstraint(
            "tenant_id",
            "contribution_key",
            "sanitized_content_hash",
            name="uq_eligible_contributions_idempotent",
        ),
        Index("ix_eligible_contributions_tenant_status", "tenant_id", "eligibility_status"),
        Index("ix_eligible_contributions_tenant_assessed", "tenant_id", "assessed_at"),
        Index("ix_eligible_contributions_hash", "sanitized_content_hash"),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Stable internal key chosen by the assessor (e.g. batch or snapshot id).
    contribution_key: Mapped[str] = mapped_column(String(128), nullable=False)
    source_dataset_ref: Mapped[str] = mapped_column(String(500), nullable=False)
    policy_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    policy_contract_version: Mapped[str] = mapped_column(String(80), nullable=False)
    modality: Mapped[str] = mapped_column(String(32), nullable=False)
    eligibility_status: Mapped[str] = mapped_column(String(32), nullable=False)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    approval_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    sanitized_content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    anonymization_rules_version: Mapped[str] = mapped_column(String(40), nullable=False)
    feature_schema_version: Mapped[str] = mapped_column(String(40), nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    assessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    assessed_by_admin_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("mira_control_admins.id", ondelete="SET NULL"),
        nullable=True,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
