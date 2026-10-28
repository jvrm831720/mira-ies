"""Historical snapshots of real risk assessments."""
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, Float, ForeignKey, ForeignKeyConstraint, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RiskAssessment(Base):
    __tablename__ = "risk_assessments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "student_id"],
            ["students.tenant_id", "students.id"],
            name="fk_risk_assessments_tenant_student",
            ondelete="CASCADE",
        ),
        UniqueConstraint("scoring_run_id", "student_id", name="uq_risk_assessments_run_student"),
        Index("ix_risk_assessments_tenant_evaluated", "tenant_id", "evaluated_at"),
        Index("ix_risk_assessments_tenant_student_evaluated", "tenant_id", "student_id", "evaluated_at"),
        Index("ix_risk_assessments_tenant_level_evaluated", "tenant_id", "risk_level", "evaluated_at"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    student_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    batch_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("upload_batches.id", ondelete="SET NULL"), nullable=True
    )
    scoring_run_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    score_semantics_version: Mapped[str] = mapped_column(String(40), nullable=False, default="risk-score-v1")
    model_scope: Mapped[str] = mapped_column(String(20), nullable=False)
    model_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    dynamic_adjustment: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    features_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    explanation: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    context: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
