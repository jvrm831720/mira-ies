"""Tenant-scoped student service requests, documents and financial references."""
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def utcnow():
    return datetime.now(timezone.utc)


class StudentServiceRequest(Base):
    __tablename__ = "mira_student_service_requests"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_mira_service_request_tenant_id"),
        ForeignKeyConstraint(["tenant_id", "student_id"], ["students.tenant_id", "students.id"], name="fk_mira_request_student_tenant"),
        CheckConstraint("status IN ('submitted','in_review','approved','rejected','completed','cancelled')", name="ck_mira_service_request_status"),
        Index("ix_mira_service_request_student", "tenant_id", "student_id", "created_at"),
    )
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False)
    student_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    subject: Mapped[str] = mapped_column(String(180), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="submitted")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class StudentServiceEvent(Base):
    __tablename__ = "mira_student_service_events"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "request_id"], ["mira_student_service_requests.tenant_id", "mira_student_service_requests.id"], name="fk_mira_service_event_request_tenant"),
        Index("ix_mira_service_event_request", "tenant_id", "request_id", "occurred_at"),
    )
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False)
    request_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_user_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False))
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    note: Mapped[str | None] = mapped_column(String(500))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class StudentDocument(Base):
    __tablename__ = "mira_student_documents"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_mira_student_document_tenant_id"),
        ForeignKeyConstraint(["tenant_id", "student_id"], ["students.tenant_id", "students.id"], name="fk_mira_document_student_tenant"),
        CheckConstraint("publication_status IN ('draft','published','revoked')", name="ck_mira_document_publication"),
        Index("ix_mira_document_student", "tenant_id", "student_id", "created_at"),
    )
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False)
    student_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    kind: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    content_text: Mapped[str] = mapped_column(Text, nullable=False)
    publication_status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class StudentFinancialReference(Base):
    __tablename__ = "mira_student_financial_references"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "student_id"], ["students.tenant_id", "students.id"], name="fk_mira_financial_reference_student_tenant"),
        UniqueConstraint("tenant_id", "student_id", "source", "external_id", name="uq_mira_financial_reference_source"),
        CheckConstraint("amount >= 0", name="ck_mira_financial_reference_amount"),
        Index("ix_mira_financial_reference_student", "tenant_id", "student_id"),
    )
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False)
    student_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    source: Mapped[str] = mapped_column(String(60), nullable=False)
    external_id: Mapped[str] = mapped_column(String(120), nullable=False)
    label: Mapped[str] = mapped_column(String(180), nullable=False)
    amount: Mapped[object] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="BRL")
    due_on: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_status: Mapped[str] = mapped_column(String(50), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
