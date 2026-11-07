"""Versioned tenant-scoped Object Index configurations, not record copies."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ObjectView(Base):
    __tablename__ = "mira_object_views"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_mira_object_views_tenant_id"),
        UniqueConstraint("tenant_id", "owner_user_id", "object_key", "name", name="uq_mira_object_views_owner_name"),
        CheckConstraint("scope IN ('personal','workspace')", name="ck_mira_object_views_scope"),
        CheckConstraint("revision >= 1", name="ck_mira_object_views_revision"),
        Index("ix_mira_object_views_owner", "tenant_id", "owner_user_id", "object_key"),
        Index("ix_mira_object_views_shared", "tenant_id", "object_key", "scope"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    owner_user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("mira_users.id", ondelete="CASCADE"), nullable=False)
    object_key: Mapped[str] = mapped_column(String(36), nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    scope: Mapped[str] = mapped_column(String(16), nullable=False, default="personal")
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_sensitive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    config_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class ObjectViewRevision(Base):
    __tablename__ = "mira_object_view_revisions"
    __table_args__ = (
        UniqueConstraint("view_id", "revision", name="uq_mira_object_view_revision"),
        ForeignKeyConstraint(["tenant_id", "view_id"], ["mira_object_views.tenant_id", "mira_object_views.id"], ondelete="CASCADE"),
        CheckConstraint("revision >= 1", name="ck_mira_object_view_revision_positive"),
        Index("ix_mira_object_view_revisions_tenant", "tenant_id", "view_id", "revision"),
    )
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    view_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    edited_by_user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("mira_users.id", ondelete="SET NULL"), nullable=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    scope: Mapped[str] = mapped_column(String(16), nullable=False)
    config_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False)
    is_sensitive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class ObjectViewFavorite(Base):
    __tablename__ = "mira_object_view_favorites"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "view_id"], ["mira_object_views.tenant_id", "mira_object_views.id"], ondelete="CASCADE"),
        Index("ix_mira_view_favorites_user", "tenant_id", "user_id"),
    )
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("mira_users.id", ondelete="CASCADE"), primary_key=True)
    view_id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
