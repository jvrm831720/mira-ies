"""Tenant-scoped connection from MIRA to its self-hosted Frappe Education engine.

A tenant is bound to one immutable Frappe site. Student links must be verified
explicitly; matrícula/email matching alone is never considered authorization.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, ForeignKeyConstraint, Index, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TenantEducationEngineConnection(Base):
    __tablename__ = "tenant_education_engine_connections"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_education_engine_tenant"),
        UniqueConstraint("site_name", name="uq_education_engine_site"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    site_name: Mapped[str] = mapped_column(String(200), nullable=False)
    encrypted_api_key: Mapped[str] = mapped_column(Text, nullable=False)
    encrypted_api_secret: Mapped[str] = mapped_column(Text, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="configured")
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now,
    )


class TenantEducationEngineStudent(Base):
    __tablename__ = "tenant_education_engine_students"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "student_id"], ["students.tenant_id", "students.id"],
            name="fk_education_engine_tenant_student", ondelete="CASCADE",
        ),
        UniqueConstraint("tenant_id", "student_id", name="uq_education_engine_local_student"),
        UniqueConstraint("tenant_id", "frappe_student_id", name="uq_education_engine_remote_student"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False,
    )
    student_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    frappe_student_id: Mapped[str] = mapped_column(String(180), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)


class TenantEducationEngineAudit(Base):
    __tablename__ = "tenant_education_engine_audit"
    __table_args__ = (Index("ix_education_engine_audit_tenant_time", "tenant_id", "occurred_at"),)

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_user_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False))
    student_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)
