"""Tenant-scoped student service requests, documents and financial references."""
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, LargeBinary, Numeric, String, Text, UniqueConstraint
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
        Index("ix_mira_service_work_queue", "tenant_id", "status", "due_at", "created_at"),
        Index("ix_mira_service_assignee_queue", "tenant_id", "assigned_membership_id", "status"),
        ForeignKeyConstraint(["tenant_id", "assigned_membership_id"], ["mira_memberships.tenant_id", "mira_memberships.id"], name="fk_mira_service_assignee_membership_tenant"),
        ForeignKeyConstraint(["tenant_id", "generated_document_id"], ["mira_student_documents.tenant_id", "mira_student_documents.id"], name="fk_mira_service_generated_document_tenant"),
        CheckConstraint("priority IN ('low','normal','high','urgent')", name="ck_mira_service_request_priority"),
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
    assigned_membership_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False))
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    priority: Mapped[str] = mapped_column(String(12), nullable=False, default="normal")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    generated_document_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False))


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


class StudentServiceComment(Base):
    __tablename__ = "mira_student_service_comments"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "request_id"], ["mira_student_service_requests.tenant_id", "mira_student_service_requests.id"], name="fk_mira_service_comment_request_tenant"),
        Index("ix_mira_service_comment_request", "tenant_id", "request_id", "created_at"),
        CheckConstraint("actor_type IN ('staff','student')", name="ck_mira_service_comment_actor"),
        CheckConstraint("visibility IN ('student','staff')", name="ck_mira_service_comment_visibility"),
        CheckConstraint("actor_type != 'student' OR visibility = 'student'", name="ck_mira_service_student_comment_public"),
        CheckConstraint("length(body) BETWEEN 1 AND 2000", name="ck_mira_service_comment_length"),
    )
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False)
    request_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(12), nullable=False)
    actor_user_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False))
    visibility: Mapped[str] = mapped_column(String(12), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class StudentServiceAttachment(Base):
    __tablename__ = "mira_student_service_attachments"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "request_id"], ["mira_student_service_requests.tenant_id", "mira_student_service_requests.id"], name="fk_mira_service_attachment_request_tenant"),
        Index("ix_mira_service_attachment_request", "tenant_id", "request_id", "created_at"),
        CheckConstraint("actor_type IN ('staff','student')", name="ck_mira_service_attachment_actor"),
        CheckConstraint("visibility IN ('student','staff')", name="ck_mira_service_attachment_visibility"),
        CheckConstraint("actor_type != 'student' OR visibility = 'student'", name="ck_mira_service_student_attachment_public"),
        CheckConstraint("byte_count BETWEEN 1 AND 262144", name="ck_mira_service_attachment_length"),
    )
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False)
    request_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(12), nullable=False)
    actor_user_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False))
    visibility: Mapped[str] = mapped_column(String(12), nullable=False)
    filename: Mapped[str] = mapped_column(String(160), nullable=False)
    content_type: Mapped[str] = mapped_column(String(60), nullable=False)
    byte_count: Mapped[int] = mapped_column(Integer, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    content: Mapped[bytes] = mapped_column(LargeBinary(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class StudentServiceNotification(Base):
    __tablename__ = "mira_student_service_notifications"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "request_id"], ["mira_student_service_requests.tenant_id", "mira_student_service_requests.id"], name="fk_mira_service_notification_request_tenant"),
        ForeignKeyConstraint(["tenant_id", "student_id"], ["students.tenant_id", "students.id"], name="fk_mira_service_notification_student_tenant"),
        Index("ix_mira_service_notification_recipient", "tenant_id", "recipient_kind", "staff_user_id", "student_id", "read_at"),
        CheckConstraint("(recipient_kind = 'student' AND student_id IS NOT NULL AND staff_user_id IS NULL) OR (recipient_kind = 'staff' AND staff_user_id IS NOT NULL AND student_id IS NULL)", name="ck_mira_service_notification_recipient"),
    )
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False)
    request_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    recipient_kind: Mapped[str] = mapped_column(String(12), nullable=False)
    student_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False))
    staff_user_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("mira_users.id"))
    event_key: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class StudentDocumentTemplate(Base):
    __tablename__ = "mira_student_document_templates"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_mira_service_template_tenant_id"),
        UniqueConstraint("tenant_id", "name", name="uq_mira_service_template_tenant_name"),
        CheckConstraint("length(body_template) BETWEEN 10 AND 10000", name="ck_mira_service_template_length"),
    )
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    document_kind: Mapped[str] = mapped_column(String(50), nullable=False)
    body_template: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by_user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
