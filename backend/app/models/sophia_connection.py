"""Tenant-scoped SophiA connection and student identity mapping."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, ForeignKeyConstraint, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TenantSophiaConnection(Base):
    __tablename__ = "tenant_sophia_connections"
    __table_args__ = (UniqueConstraint("tenant_id", name="uq_tenant_sophia_connections_tenant"),)

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    encrypted_username: Mapped[str] = mapped_column(Text, nullable=False)
    encrypted_password: Mapped[str] = mapped_column(Text, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="configured", nullable=False)
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, onupdate=_utc_now, nullable=False)


class TenantSophiaStudentLink(Base):
    __tablename__ = "tenant_sophia_student_links"
    __table_args__ = (
        UniqueConstraint("tenant_id", "student_id", name="uq_tenant_sophia_student_links_student"),
        UniqueConstraint("tenant_id", "codigo_interno", name="uq_tenant_sophia_student_links_codigo"),
        ForeignKeyConstraint(
            ["tenant_id", "student_id"], ["students.tenant_id", "students.id"],
            ondelete="CASCADE", name="fk_tenant_sophia_student_links_student_tenant",
        ),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    codigo_interno: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    created_by_user_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("mira_users.id", ondelete="SET NULL"), nullable=True)
