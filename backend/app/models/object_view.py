"""Per-user Object Index view metadata. No record contents are stored."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base

class ObjectView(Base):
    __tablename__ = "mira_object_views"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_mira_object_views_tenant_id"),
        UniqueConstraint("tenant_id", "owner_user_id", "object_key", "name", name="uq_mira_object_views_owner_name"),
        Index("ix_mira_object_views_owner", "tenant_id", "owner_user_id", "object_key"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    owner_user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("mira_users.id", ondelete="CASCADE"), nullable=False)
    object_key: Mapped[str] = mapped_column(String(36), nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    config_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
