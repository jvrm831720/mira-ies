"""Immutable document provenance with explicit revocation. Not an ICP-Brasil signature."""
from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, ForeignKeyConstraint, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class StudentDocumentAttestation(Base):
    __tablename__ = "mira_student_document_attestations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_student_attestation_tenant_id"),
        UniqueConstraint("tenant_id", "document_id", name="uq_student_attestation_document"),
        ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["mira_student_documents.tenant_id", "mira_student_documents.id"],
            name="fk_student_attestation_document_tenant",
        ),
        Index("ix_student_attestation_document", "tenant_id", "document_id"),
    )
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False)
    document_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    student_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    issued_by_user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("mira_users.id"), nullable=False)
    signing_key_id: Mapped[str] = mapped_column(String(40), nullable=False)
    content_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    signature: Mapped[str] = mapped_column(String(64), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_by_user_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False))
