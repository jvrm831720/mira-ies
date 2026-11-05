"""Audit of Composio financial reads; never a payment or receipt."""
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class StudentFinancialSyncRun(Base):
    __tablename__ = "mira_student_financial_sync_runs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_student_finance_sync_tenant_id"),
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_student_finance_sync_key"),
        Index("ix_student_finance_sync_tenant_time", "tenant_id", "synced_at"),
    )
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False)
    actor_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    connected_account_id: Mapped[str] = mapped_column(String(120), nullable=False)
    toolkit: Mapped[str] = mapped_column(String(80), nullable=False)
    tool_slug: Mapped[str] = mapped_column(String(120), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    record_count: Mapped[int] = mapped_column(Integer, nullable=False)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
