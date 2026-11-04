"""Campanhas de retenção e versões imutáveis de regras por tenant."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RetentionCampaign(Base):
    __tablename__ = "retention_campaigns"
    __table_args__ = (
        UniqueConstraint("tenant_id", "slug", "version", name="uq_retention_campaign_tenant_slug_version"),
        Index(
            "uq_retention_campaigns_one_active_version",
            "tenant_id",
            "slug",
            unique=True,
            postgresql_where=text("status = 'active' AND archived IS FALSE"),
        ),
        Index("ix_retention_campaigns_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    rules: Mapped[list] = mapped_column(JSONB, nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class RetentionCampaignProposal(Base):
    """Draft proposal with a database-enforced immutable audience snapshot."""

    __tablename__ = "retention_campaign_proposals"
    __table_args__ = (
        Index("ix_retention_campaign_proposals_tenant_created", "tenant_id", "created_at"),
        Index("ix_retention_campaign_proposals_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    source_group_ids: Mapped[list] = mapped_column(JSONB, nullable=False)
    source_catalog_version: Mapped[str] = mapped_column(String(40), nullable=False)
    recommendation_engine: Mapped[str] = mapped_column(String(60), nullable=False)
    source_evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    strategy: Mapped[str] = mapped_column(Text, nullable=False)
    recommended_channels: Mapped[list] = mapped_column(JSONB, nullable=False)
    cadence_days: Mapped[list] = mapped_column(JSONB, nullable=False)
    message_brief: Mapped[str] = mapped_column(Text, nullable=False)
    audience_snapshot: Mapped[list] = mapped_column(JSONB, nullable=False)
    audience_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    audience_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    outreach_eligible_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    blocked_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    internal_action_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class RetentionCampaignProposalAuditEvent(Base):
    """Append-only audit trail for proposal editing, review and approval."""

    __tablename__ = "retention_campaign_proposal_audit_events"
    __table_args__ = (
        Index("ix_retention_proposal_audit_tenant_proposal", "tenant_id", "proposal_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    proposal_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("retention_campaign_proposals.id", ondelete="CASCADE"), nullable=False
    )
    actor_user_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("mira_users.id", ondelete="SET NULL"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
