"""Explicit tenant grants and isolated financial snapshots for the global portal."""
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base


def now():
    return datetime.now(timezone.utc)


class GlobalDebtGrant(Base):
    __tablename__ = "mira_global_debt_grants"
    __table_args__ = (
        CheckConstraint("state IN ('pending','accepted','revoked')", name="ck_global_debt_grant_state"),
        UniqueConstraint("tenant_id", "student_id", "account_id", name="uq_global_debt_grant"),
        ForeignKeyConstraint(["tenant_id", "student_id"], ["students.tenant_id", "students.id"],
                             name="fk_global_debt_grant_student_tenant"),
        Index("ix_global_debt_grant_account", "account_id", "state"),
        Index("ix_global_debt_grant_tenant", "tenant_id", "student_id"),
    )
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    account_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("mira_global_student_accounts.id"), nullable=False)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False)
    student_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    evidence_reference: Mapped[str] = mapped_column(String(120), nullable=False)
    created_by: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class GlobalDebtSnapshot(Base):
    __tablename__ = "mira_global_debt_snapshots"
    __table_args__ = (
        UniqueConstraint("grant_id", "observation_id", name="uq_global_debt_snapshot"),
        CheckConstraint("amount >= 0 AND paid_amount >= 0 AND paid_amount <= amount",
                        name="ck_global_debt_snapshot_amounts"),
        Index("ix_global_debt_snapshot_grant", "grant_id"),
    )
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    grant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("mira_global_debt_grants.id", ondelete="CASCADE"), nullable=False)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False)
    observation_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    label: Mapped[str] = mapped_column(String(180), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    snapshotted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now)
