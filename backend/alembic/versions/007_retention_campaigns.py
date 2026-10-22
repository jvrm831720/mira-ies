"""Retention campaigns.
Revision ID: 007_retention_campaigns
Revises: 006_safe_agent_delivery
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "007_retention_campaigns"
down_revision = "006_safe_agent_delivery"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "retention_campaigns",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("rules", postgresql.JSONB(), nullable=False),
        sa.Column("created_by", sa.String(80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.UniqueConstraint("tenant_id", "slug", "version", name="uq_retention_campaign_tenant_slug_version"),
    )
    op.create_index("ix_retention_campaigns_tenant_id", "retention_campaigns", ["tenant_id"])
    op.create_index("ix_retention_campaigns_tenant_status", "retention_campaigns", ["tenant_id", "status"])


def downgrade():
    op.drop_index("ix_retention_campaigns_tenant_status", table_name="retention_campaigns")
    op.drop_index("ix_retention_campaigns_tenant_id", table_name="retention_campaigns")
    op.drop_table("retention_campaigns")
