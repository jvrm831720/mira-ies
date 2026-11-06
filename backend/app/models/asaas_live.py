"""Asaas official payment lifecycle (Wave 4D-B).

Mutable charge projection is separate from append-only incoming event evidence.
Every tenant-scoped child relation is protected by composite FKs and FORCE RLS.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import (
    Boolean, CheckConstraint, Date, DateTime, ForeignKey, ForeignKeyConstraint,
    Index, Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AsaasCustomerBinding(Base):
    __tablename__ = "mira_asaas_customer_bindings"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_mira_asaas_customer_tenant_id"),
        UniqueConstraint("tenant_id", "student_id", name="uq_mira_asaas_customer_student"),
        UniqueConstraint("tenant_id", "asaas_customer_id", name="uq_mira_asaas_customer_external"),
        ForeignKeyConstraint(["tenant_id", "student_id"], ["students.tenant_id", "students.id"], name="fk_mira_asaas_customer_student_tenant"),
    )
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False)
    student_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    asaas_customer_id: Mapped[str] = mapped_column(String(80), nullable=False)
    issuer_environment: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class AsaasCharge(Base):
    __tablename__ = "mira_asaas_charges"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_mira_asaas_charge_tenant_id"),
        UniqueConstraint("tenant_id", "intent_id", name="uq_mira_asaas_charge_intent"),
        UniqueConstraint("external_reference", name="uq_mira_asaas_charge_reference"),
        UniqueConstraint("asaas_payment_id", name="uq_mira_asaas_charge_payment_id"),
        ForeignKeyConstraint(["tenant_id", "intent_id"], ["mira_student_payment_intents.tenant_id", "mira_student_payment_intents.id"], name="fk_mira_asaas_charge_intent_tenant"),
        ForeignKeyConstraint(["tenant_id", "student_id"], ["students.tenant_id", "students.id"], name="fk_mira_asaas_charge_student_tenant"),
        CheckConstraint("environment IN ('sandbox','production')", name="ck_mira_asaas_charge_environment"),
        CheckConstraint("creation_state IN ('prepared','submitting','unknown','created','rejected','review')", name="ck_mira_asaas_charge_creation"),
        CheckConstraint("amount > 0 AND currency = 'BRL'", name="ck_mira_asaas_charge_amount"),
        CheckConstraint("method IN ('pix','boleto')", name="ck_mira_asaas_charge_method"),
        Index("ix_mira_asaas_charge_tenant_created", "tenant_id", "created_at"),
    )
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False)
    intent_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    student_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="BRL")
    method: Mapped[str] = mapped_column(String(12), nullable=False)
    due_date: Mapped[datetime] = mapped_column(Date, nullable=False)
    customer_id: Mapped[str] = mapped_column(String(80), nullable=False)
    destination_wallet_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    destination_version: Mapped[int] = mapped_column(nullable=False)
    environment: Mapped[str] = mapped_column(String(16), nullable=False)
    external_reference: Mapped[str] = mapped_column(String(100), nullable=False)
    asaas_payment_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    creation_state: Mapped[str] = mapped_column(String(18), nullable=False, default="prepared")
    provider_payment_status: Mapped[str] = mapped_column(String(28), nullable=False, default="UNKNOWN")
    provider_split_status: Mapped[str] = mapped_column(String(28), nullable=False, default="UNKNOWN")
    provider_split_id: Mapped[str | None] = mapped_column(String(80))
    payment_received_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    split_settled_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reconciliation_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class AsaasWebhookEvent(Base):
    __tablename__ = "mira_asaas_webhook_events"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_mira_asaas_event_tenant_id"),
        UniqueConstraint("event_id", name="uq_mira_asaas_event_global_id"),
        ForeignKeyConstraint(["tenant_id", "charge_id"], ["mira_asaas_charges.tenant_id", "mira_asaas_charges.id"], name="fk_mira_asaas_event_charge_tenant"),
        Index("ix_mira_asaas_event_pending", "tenant_id", "received_at"),
    )
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False)
    charge_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    event_id: Mapped[str] = mapped_column(String(120), nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    payment_id: Mapped[str] = mapped_column(String(80), nullable=False)
    split_id: Mapped[str | None] = mapped_column(String(100))
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class AsaasWebhookApplication(Base):
    __tablename__ = "mira_asaas_webhook_applications"
    __table_args__ = (
        UniqueConstraint("tenant_id", "event_id", name="uq_mira_asaas_applied_event"),
        ForeignKeyConstraint(["tenant_id", "event_id"], ["mira_asaas_webhook_events.tenant_id", "mira_asaas_webhook_events.id"], name="fk_mira_asaas_application_event_tenant"),
        Index("ix_mira_asaas_application_tenant", "tenant_id", "applied_at"),
    )
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False)
    event_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_status: Mapped[str] = mapped_column(String(40), nullable=False)
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
