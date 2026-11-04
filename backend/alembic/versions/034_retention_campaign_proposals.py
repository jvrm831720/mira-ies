"""Persist retention campaign proposals with immutable audience snapshots.

Revision ID: 034_retention_campaign_proposals
Revises: 033_sophia_sync_jobs
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "034_retention_campaign_proposals"
down_revision = "033_sophia_sync_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "retention_campaign_proposals",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("source_group_ids", postgresql.JSONB(), nullable=False),
        sa.Column("source_catalog_version", sa.String(40), nullable=False),
        sa.Column("recommendation_engine", sa.String(60), nullable=False),
        sa.Column("source_evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("strategy", sa.Text(), nullable=False),
        sa.Column("recommended_channels", postgresql.JSONB(), nullable=False),
        sa.Column("cadence_days", postgresql.JSONB(), nullable=False),
        sa.Column("message_brief", sa.Text(), nullable=False),
        sa.Column("audience_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("audience_hash", sa.String(64), nullable=False),
        sa.Column("audience_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("outreach_eligible_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("blocked_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("internal_action_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by", sa.String(80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("status IN ('draft')", name="ck_retention_campaign_proposals_status"),
        sa.CheckConstraint("audience_total >= 0 AND outreach_eligible_count >= 0 AND blocked_count >= 0 AND internal_action_count >= 0", name="ck_retention_campaign_proposals_counts"),
    )
    op.create_index("ix_retention_campaign_proposals_tenant_id", "retention_campaign_proposals", ["tenant_id"])
    op.create_index("ix_retention_campaign_proposals_tenant_created", "retention_campaign_proposals", ["tenant_id", "created_at"])
    op.create_index("ix_retention_campaign_proposals_tenant_status", "retention_campaign_proposals", ["tenant_id", "status"])
    op.execute("""
        CREATE FUNCTION prevent_retention_proposal_snapshot_mutation()
        RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                -- Permit tenant-level cascade deletion, but reject direct proposal deletion.
                IF EXISTS (SELECT 1 FROM tenants WHERE id = OLD.tenant_id) THEN
                    RAISE EXCEPTION 'Retention campaign proposal snapshots cannot be deleted'
                        USING ERRCODE = 'check_violation';
                END IF;
                RETURN OLD;
            END IF;
            IF NEW.source_group_ids IS DISTINCT FROM OLD.source_group_ids
               OR NEW.source_catalog_version IS DISTINCT FROM OLD.source_catalog_version
               OR NEW.recommendation_engine IS DISTINCT FROM OLD.recommendation_engine
               OR NEW.source_evaluated_at IS DISTINCT FROM OLD.source_evaluated_at
               OR NEW.audience_snapshot IS DISTINCT FROM OLD.audience_snapshot
               OR NEW.audience_hash IS DISTINCT FROM OLD.audience_hash
               OR NEW.audience_total IS DISTINCT FROM OLD.audience_total
               OR NEW.outreach_eligible_count IS DISTINCT FROM OLD.outreach_eligible_count
               OR NEW.blocked_count IS DISTINCT FROM OLD.blocked_count
               OR NEW.internal_action_count IS DISTINCT FROM OLD.internal_action_count
            THEN
                RAISE EXCEPTION 'Retention campaign proposal audience snapshot is immutable'
                    USING ERRCODE = 'check_violation';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER trg_retention_proposal_snapshot_immutable
        BEFORE UPDATE OR DELETE ON retention_campaign_proposals
        FOR EACH ROW EXECUTE FUNCTION prevent_retention_proposal_snapshot_mutation();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_retention_proposal_snapshot_immutable ON retention_campaign_proposals")
    op.execute("DROP FUNCTION IF EXISTS prevent_retention_proposal_snapshot_mutation()")
    op.drop_index("ix_retention_campaign_proposals_tenant_status", table_name="retention_campaign_proposals")
    op.drop_index("ix_retention_campaign_proposals_tenant_created", table_name="retention_campaign_proposals")
    op.drop_index("ix_retention_campaign_proposals_tenant_id", table_name="retention_campaign_proposals")
    op.drop_table("retention_campaign_proposals")
