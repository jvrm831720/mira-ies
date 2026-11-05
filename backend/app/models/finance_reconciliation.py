"""Metadata-defined financial sources, verified student links and auditable observations.

Workspace customization lives in constrained JSONB metadata, not per-tenant DDL.
Composio account IDs and import profiles are independent, so a workspace can
configure multiple financial sources with different mappings and review flows.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint,
    Index, Integer, Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class FinanceSourceProfile(Base):
    __tablename__ = "mira_finance_source_profiles"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_mira_finance_profile_tenant_id"),
        UniqueConstraint("tenant_id", "name", name="uq_mira_finance_profile_tenant_name"),
        CheckConstraint("source_kind IN ('composio','import')", name="ck_mira_finance_profile_kind"),
        CheckConstraint("mapping_version > 0", name="ck_mira_finance_mapping_version"),
        Index("ix_mira_finance_profiles_tenant_kind", "tenant_id", "source_kind"),
    )
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    source_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    connected_account_id: Mapped[str | None] = mapped_column(String(120))
    tool_slug: Mapped[str | None] = mapped_column(String(120))
    rows_path: Mapped[str] = mapped_column(String(240), nullable=False, default="")
    field_map: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status_map: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    review_workflow: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    student_lookup: Mapped[str] = mapped_column(String(20), nullable=False, default="mira_id")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    mapping_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class FinanceStudentLink(Base):
    __tablename__ = "mira_finance_student_links"
    __table_args__ = (
        UniqueConstraint("tenant_id", "profile_id", "external_student_ref", name="uq_mira_finance_student_source_ref"),
        ForeignKeyConstraint(
            ["tenant_id", "profile_id"], ["mira_finance_source_profiles.tenant_id", "mira_finance_source_profiles.id"],
            name="fk_mira_finance_link_profile_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "student_id"], ["students.tenant_id", "students.id"],
            name="fk_mira_finance_link_student_tenant",
        ),
        Index("ix_mira_finance_link_student", "tenant_id", "student_id"),
    )
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False)
    profile_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    external_student_ref: Mapped[str] = mapped_column(String(120), nullable=False)
    student_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    verified_by: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class FinanceIngestionBatch(Base):
    __tablename__ = "mira_finance_ingestion_batches"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_mira_finance_batch_tenant_id"),
        UniqueConstraint("tenant_id", "profile_id", "idempotency_key", name="uq_mira_finance_batch_idempotency"),
        ForeignKeyConstraint(
            ["tenant_id", "profile_id"], ["mira_finance_source_profiles.tenant_id", "mira_finance_source_profiles.id"],
            name="fk_mira_finance_batch_profile_tenant",
        ),
        CheckConstraint("row_count >= 0 AND row_count <= 100", name="ck_mira_finance_batch_row_count"),
    )
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False)
    profile_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    actor_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    origin: Mapped[str] = mapped_column(String(20), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    payload_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    mapping_version: Mapped[int] = mapped_column(Integer, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    imported_count: Mapped[int] = mapped_column(Integer, nullable=False)
    unchanged_count: Mapped[int] = mapped_column(Integer, nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class FinanceObservation(Base):
    __tablename__ = "mira_finance_observations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "profile_id", "fingerprint", name="uq_mira_finance_observation_dedup"),
        ForeignKeyConstraint(
            ["tenant_id", "profile_id"], ["mira_finance_source_profiles.tenant_id", "mira_finance_source_profiles.id"],
            name="fk_mira_finance_obs_profile_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "student_id"], ["students.tenant_id", "students.id"],
            name="fk_mira_finance_obs_student_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "batch_id"], ["mira_finance_ingestion_batches.tenant_id", "mira_finance_ingestion_batches.id"],
            name="fk_mira_finance_obs_batch_tenant",
        ),
        CheckConstraint("amount >= 0 AND paid_amount >= 0 AND paid_amount <= amount", name="ck_mira_finance_obs_amounts"),
        CheckConstraint(
            "canonical_state IN ('open','overdue','partially_paid','reported_paid','cancelled','disputed','unknown')",
            name="ck_mira_finance_obs_state",
        ),
        Index("ix_mira_finance_obs_reconciliation", "tenant_id", "student_id", "correlation_key"),
        Index("ix_mira_finance_obs_source", "tenant_id", "profile_id", "external_id", "observed_at"),
    )
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False)
    profile_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    student_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    batch_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    external_id: Mapped[str] = mapped_column(String(120), nullable=False)
    correlation_key: Mapped[str | None] = mapped_column(String(120))
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(180), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    canonical_state: Mapped[str] = mapped_column(String(20), nullable=False)
    raw_status: Mapped[str] = mapped_column(String(50), nullable=False)
    mapping_version: Mapped[int] = mapped_column(Integer, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class FinanceReviewCase(Base):
    __tablename__ = "mira_finance_review_cases"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_mira_finance_case_tenant_id"),
        UniqueConstraint("tenant_id", "profile_id", "external_id", name="uq_mira_finance_case_source"),
        ForeignKeyConstraint(
            ["tenant_id", "profile_id"], ["mira_finance_source_profiles.tenant_id", "mira_finance_source_profiles.id"],
            name="fk_mira_finance_case_profile_tenant",
        ),
        CheckConstraint("step ~ '^[a-z][a-z0-9_]{0,23}$'", name="ck_mira_finance_case_step"),
        Index("ix_mira_finance_case_tenant_step", "tenant_id", "step"),
    )
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False)
    profile_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    external_id: Mapped[str] = mapped_column(String(120), nullable=False)
    step: Mapped[str] = mapped_column(String(24), nullable=False, default="open")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    updated_by: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class FinanceReviewEvent(Base):
    __tablename__ = "mira_finance_review_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "case_id"], ["mira_finance_review_cases.tenant_id", "mira_finance_review_cases.id"],
            name="fk_mira_finance_review_case_tenant",
        ),
        Index("ix_mira_finance_review_history", "tenant_id", "case_id", "recorded_at"),
    )
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False)
    case_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    step: Mapped[str] = mapped_column(String(24), nullable=False)
    actor_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
", name="ck_mira_finance_case_step"),
        Index("ix_mira_finance_case_tenant_step", "tenant_id", "step"),
    )
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False)
    profile_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    external_id: Mapped[str] = mapped_column(String(120), nullable=False)
    step: Mapped[str] = mapped_column(String(24), nullable=False, default="open")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    updated_by: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class FinanceReviewEvent(Base):
    __tablename__ = "mira_finance_review_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "case_id"], ["mira_finance_review_cases.tenant_id", "mira_finance_review_cases.id"],
            name="fk_mira_finance_review_case_tenant",
        ),
        Index("ix_mira_finance_review_history", "tenant_id", "case_id", "recorded_at"),
    )
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False)
    case_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    step: Mapped[str] = mapped_column(String(24), nullable=False)
    actor_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
