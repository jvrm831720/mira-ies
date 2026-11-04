"""Append-only lifecycle events for the global MIRA Base model (Wave 13.4)."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MiraBaseLifecycleEvent(Base):
    __tablename__ = "mira_base_lifecycle_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('register_candidate', 'approve', 'reject', 'activate', 'retire', 'rollback')",
            name="ck_mira_base_lifecycle_event_type",
        ),
        CheckConstraint(
            "to_status IN ('candidate', 'approved', 'active', 'retired', 'rejected')",
            name="ck_mira_base_lifecycle_to_status",
        ),
        Index("ix_mira_base_lifecycle_events_artifact", "artifact_id", "created_at"),
        Index("ix_mira_base_lifecycle_events_type", "event_type", "created_at"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    artifact_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("model_artifacts.id", ondelete="RESTRICT"), nullable=False)
    run_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("training_runs.id", ondelete="SET NULL"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    to_status: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    actor_admin_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("mira_control_admins.id", ondelete="SET NULL"), nullable=True)
    rollback_of_artifact_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("model_artifacts.id", ondelete="SET NULL"), nullable=True)
    metadata_redacted: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
