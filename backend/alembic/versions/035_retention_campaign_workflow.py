"""Proposal editing, review, approval and append-only audit trail.

Revision ID: 035_retention_campaign_workflow
Revises: 034_retention_campaign_proposals
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "035_retention_campaign_workflow"
down_revision = "034_retention_campaign_proposals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_retention_campaign_proposals_status", "retention_campaign_proposals", type_="check")
    op.create_check_constraint(
        "ck_retention_campaign_proposals_status",
        "retention_campaign_proposals",
        "status IN ('draft', 'in_review', 'changes_requested', 'approved')",
    )
    op.add_column("retention_campaign_proposals", sa.Column("revision", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("retention_campaign_proposals", sa.Column("reviewed_by", sa.String(80), nullable=True))
    op.add_column("retention_campaign_proposals", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("retention_campaign_proposals", sa.Column("approved_by", sa.String(80), nullable=True))
    op.add_column("retention_campaign_proposals", sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("retention_campaign_proposals", sa.Column("authorization_status", sa.String(32), nullable=False, server_default="not_verified"))
    op.add_column("retention_campaign_proposals", sa.Column("authorization_basis", sa.String(120), nullable=True))
    op.add_column("retention_campaign_proposals", sa.Column("authorization_reference", sa.String(160), nullable=True))
    op.add_column("retention_campaign_proposals", sa.Column("authorization_attested_by", sa.String(80), nullable=True))
    op.add_column("retention_campaign_proposals", sa.Column("authorization_attested_at", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint("ck_retention_proposal_revision_positive", "retention_campaign_proposals", "revision >= 1")
    op.create_check_constraint(
        "ck_retention_proposal_authorization_status",
        "retention_campaign_proposals",
        "authorization_status IN ('not_verified', 'institution_attested')",
    )
    op.create_table(
        "retention_campaign_proposal_audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("proposal_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("retention_campaign_proposals.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("mira_users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("details", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("revision >= 1", name="ck_retention_proposal_audit_revision_positive"),
    )
    op.create_index(
        "ix_retention_proposal_audit_tenant_proposal",
        "retention_campaign_proposal_audit_events",
        ["tenant_id", "proposal_id", "created_at"],
    )
    op.execute("""
        CREATE FUNCTION prevent_retention_proposal_audit_mutation()
        RETURNS trigger AS $$
        BEGIN
            -- Direct mutation is forbidden; parent cascades for tenant/proposal deletion remain valid.
            IF EXISTS (SELECT 1 FROM tenants WHERE id = OLD.tenant_id)
               AND EXISTS (SELECT 1 FROM retention_campaign_proposals WHERE id = OLD.proposal_id)
            THEN
                RAISE EXCEPTION 'Retention campaign proposal audit events are append-only'
                    USING ERRCODE = 'check_violation';
            END IF;
            RETURN OLD;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER trg_retention_proposal_audit_immutable
        BEFORE UPDATE OR DELETE ON retention_campaign_proposal_audit_events
        FOR EACH ROW EXECUTE FUNCTION prevent_retention_proposal_audit_mutation();
    """)
    op.execute("ALTER TABLE retention_campaign_proposal_audit_events ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE retention_campaign_proposal_audit_events FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY retention_campaign_proposal_audit_tenant_isolation
        ON retention_campaign_proposal_audit_events
        USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS retention_campaign_proposal_audit_tenant_isolation ON retention_campaign_proposal_audit_events")
    op.execute("DROP TRIGGER IF EXISTS trg_retention_proposal_audit_immutable ON retention_campaign_proposal_audit_events")
    op.execute("DROP FUNCTION IF EXISTS prevent_retention_proposal_audit_mutation()")
    op.drop_index("ix_retention_proposal_audit_tenant_proposal", table_name="retention_campaign_proposal_audit_events")
    op.drop_table("retention_campaign_proposal_audit_events")
    op.drop_constraint("ck_retention_proposal_authorization_status", "retention_campaign_proposals", type_="check")
    op.drop_constraint("ck_retention_proposal_revision_positive", "retention_campaign_proposals", type_="check")
    for column in (
        "authorization_attested_at", "authorization_attested_by", "authorization_reference",
        "authorization_basis", "authorization_status", "approved_at", "approved_by",
        "reviewed_at", "reviewed_by", "revision",
    ):
        op.drop_column("retention_campaign_proposals", column)
    op.drop_constraint("ck_retention_campaign_proposals_status", "retention_campaign_proposals", type_="check")
    op.create_check_constraint(
        "ck_retention_campaign_proposals_status",
        "retention_campaign_proposals",
        "status IN ('draft')",
    )
