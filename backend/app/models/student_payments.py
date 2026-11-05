"""Wave 4D-A payment preparation. No checkout, transfer, Pix or boleto execution."""
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base


def utcnow():
    return datetime.now(timezone.utc)


class StudentPaymentConnector(Base):
    __tablename__ = "mira_student_payment_connectors"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_mira_payment_connector_tenant_id"),
        UniqueConstraint("tenant_id", "name", name="uq_mira_payment_connector_tenant_name"),
        UniqueConstraint("tenant_id", "finance_profile_id", "destination_wallet_id", name="uq_mira_payment_finance_destination"),
        ForeignKeyConstraint(["tenant_id", "finance_profile_id"], ["mira_finance_source_profiles.tenant_id", "mira_finance_source_profiles.id"], name="fk_mira_payment_connector_finance_tenant"),
        CheckConstraint("mode = 'sandbox'", name="ck_mira_payment_connector_sandbox"),
        CheckConstraint("provider_slug = 'asaas'", name="ck_mira_payment_connector_asaas"),
        CheckConstraint("destination_verification_status IN ('pending','verified','blocked')", name="ck_mira_payment_destination_status"),
        CheckConstraint("configuration_version > 0", name="ck_mira_payment_connector_version"),
        Index("ix_mira_payment_connector_tenant", "tenant_id", "created_at"),
    )
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    provider_slug: Mapped[str] = mapped_column(String(60), nullable=False, default="asaas")
    destination_wallet_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    destination_verification_status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    finance_profile_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    mode: Mapped[str] = mapped_column(String(12), nullable=False, default="sandbox")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    configuration_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class StudentPaymentOrder(Base):
    __tablename__ = "mira_student_payment_orders"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_mira_payment_order_tenant_id"),
        UniqueConstraint("tenant_id", "connector_id", "idempotency_key", name="uq_mira_payment_order_idempotency"),
        UniqueConstraint("tenant_id", "connector_id", "observation_id", name="uq_mira_payment_order_observation_connector"),
        ForeignKeyConstraint(["tenant_id", "connector_id"], ["mira_student_payment_connectors.tenant_id", "mira_student_payment_connectors.id"], name="fk_mira_payment_order_connector_tenant"),
        ForeignKeyConstraint(["tenant_id", "observation_id"], ["mira_finance_observations.tenant_id", "mira_finance_observations.id"], name="fk_mira_payment_order_observation_tenant"),
        ForeignKeyConstraint(["tenant_id", "student_id"], ["students.tenant_id", "students.id"], name="fk_mira_payment_order_student_tenant"),
        CheckConstraint("status IN ('draft','awaiting_approval','approved','cancelled')", name="ck_mira_payment_order_status"),
        CheckConstraint("amount > 0", name="ck_mira_payment_order_amount"),
        CheckConstraint("currency = 'BRL'", name="ck_mira_payment_order_currency"),
        Index("ix_mira_payment_order_tenant_status", "tenant_id", "status", "created_at"),
        Index("ix_mira_payment_order_student", "tenant_id", "student_id", "created_at"),
    )
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False)
    connector_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    observation_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    student_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="BRL")
    source_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft")
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    requested_by: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    approved_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class StudentPaymentOrderEvent(Base):
    __tablename__ = "mira_student_payment_order_events"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "order_id"], ["mira_student_payment_orders.tenant_id", "mira_student_payment_orders.id"], name="fk_mira_payment_event_order_tenant"),
        CheckConstraint("status IN ('draft','awaiting_approval','approved','cancelled')", name="ck_mira_payment_event_status"),
        Index("ix_mira_payment_event_order", "tenant_id", "order_id", "occurred_at"),
    )
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False)
    order_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    actor_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
