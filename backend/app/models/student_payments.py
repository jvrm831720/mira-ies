"""Wave 4D: tenant-isolated provider sandbox and immutable payment evidence.

An event reported as paid is NOT a settlement confirmation.
"""
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base


def now():
    return datetime.now(timezone.utc)


class PaymentProviderProfile(Base):
    __tablename__ = "mira_payment_provider_profiles"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_mira_pay_provider_tenant_id"),
        UniqueConstraint("tenant_id", "finance_profile_id", "name", name="uq_mira_pay_provider_name"),
        ForeignKeyConstraint(["tenant_id", "finance_profile_id"], ["mira_finance_source_profiles.tenant_id", "mira_finance_source_profiles.id"], name="fk_mira_pay_provider_source_tenant"),
        CheckConstraint("connection_kind IN ('composio','custom_pending')", name="ck_mira_pay_provider_kind"),
        CheckConstraint("environment = 'sandbox'", name="ck_mira_pay_provider_sandbox"),
        Index("ix_mira_pay_provider_source", "tenant_id", "finance_profile_id"),
    )
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False)
    finance_profile_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    connection_kind: Mapped[str] = mapped_column(String(24), nullable=False)
    connected_account_id: Mapped[str | None] = mapped_column(String(120))
    provider_slug: Mapped[str] = mapped_column(String(80), nullable=False)
    methods: Mapped[list] = mapped_column(JSONB, nullable=False)
    environment: Mapped[str] = mapped_column(String(12), nullable=False, default="sandbox")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now)


class StudentPaymentIntent(Base):
    __tablename__ = "mira_student_payment_intents"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_mira_pay_intent_tenant_id"),
        UniqueConstraint("tenant_id", "provider_id", "id", name="uq_mira_pay_intent_provider_id"),
        UniqueConstraint("tenant_id", "provider_id", "idempotency_key", name="uq_mira_pay_intent_idempotency"),
        ForeignKeyConstraint(["tenant_id", "provider_id"], ["mira_payment_provider_profiles.tenant_id", "mira_payment_provider_profiles.id"], name="fk_mira_pay_intent_provider_tenant"),
        ForeignKeyConstraint(["tenant_id", "student_id"], ["students.tenant_id", "students.id"], name="fk_mira_pay_intent_student_tenant"),
        ForeignKeyConstraint(["tenant_id", "financial_observation_id"], ["mira_finance_observations.tenant_id", "mira_finance_observations.id"], name="fk_mira_pay_intent_observation_tenant"),
        CheckConstraint("amount > 0 AND amount <= 9999999999.99", name="ck_mira_pay_intent_amount"),
        CheckConstraint("currency = 'BRL'", name="ck_mira_pay_intent_currency"),
        CheckConstraint("status = 'draft'", name="ck_mira_pay_intent_draft"),
        Index("ix_mira_pay_intents_student", "tenant_id", "student_id", "created_at"),
    )
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False)
    provider_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    financial_observation_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    student_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    method: Mapped[str] = mapped_column(String(16), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="BRL")
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    created_by: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now)


class StudentPaymentEvidence(Base):
    __tablename__ = "mira_student_payment_evidence"
    __table_args__ = (
        UniqueConstraint("tenant_id", "provider_id", "provider_event_id", name="uq_mira_pay_event_id"),
        ForeignKeyConstraint(["tenant_id", "provider_id", "intent_id"], ["mira_student_payment_intents.tenant_id", "mira_student_payment_intents.provider_id", "mira_student_payment_intents.id"], name="fk_mira_pay_evidence_intent_provider_tenant"),
        CheckConstraint("reported_state IN ('created','processing','partially_paid_reported','paid_reported','failed','refunded_reported','chargeback_reported')", name="ck_mira_pay_evidence_state"),
        CheckConstraint("reported_amount >= 0", name="ck_mira_pay_evidence_amount"),
        CheckConstraint("currency = 'BRL'", name="ck_mira_pay_evidence_currency"),
        Index("ix_mira_pay_evidence_intent", "tenant_id", "intent_id", "received_at"),
    )
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False)
    provider_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    intent_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    provider_event_id: Mapped[str] = mapped_column(String(120), nullable=False)
    reported_state: Mapped[str] = mapped_column(String(32), nullable=False)
    reported_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    signature_type: Mapped[str] = mapped_column(String(40), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now)

class AsaasWorkspaceDestination(Base):
    """Single net-revenue destination for an entire workspace, independent of ERP sources.

    Only the Asaas wallet UUID is accepted; bank coordinates are not stored.
    Ownership verification is an independent compliance step, not inferred from
    a submitted wallet ID or an imported financial record.
    """
    __tablename__ = "mira_asaas_workspace_destinations"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_mira_asaas_destination_tenant"),
        CheckConstraint("status IN ('pending','verified','rejected')", name="ck_mira_asaas_destination_status"),
        CheckConstraint("version >= 1", name="ck_mira_asaas_destination_version"),
    )
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False)
    wallet_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    confirmed_by_user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_by_user_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now)
