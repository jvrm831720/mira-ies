"""Add priority, campaign origin and idempotent campaign task generation.

Revision ID: 036_work_activity_priority_campaign
Revises: 036_retention_campaign_lifecycle
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "036_work_activity_priority_campaign"
down_revision = "036_retention_campaign_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "work_activities",
        sa.Column("priority", sa.String(length=20), nullable=False, server_default="normal"),
    )
    op.add_column(
        "work_activities",
        sa.Column("origin_type", sa.String(length=20), nullable=False, server_default="manual"),
    )
    op.add_column(
        "work_activities",
        sa.Column(
            "campaign_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("retention_campaigns.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column("work_activities", sa.Column("source_key", sa.String(length=255), nullable=True))

    # Preserve campaign provenance for activities already linked to campaign logs.
    op.execute(
        """
        UPDATE work_activities AS activity
        SET origin_type = 'campaign', campaign_id = campaign.id
        FROM intervention_logs AS log
        JOIN retention_campaigns AS campaign
          ON campaign.id::text = log.campaign_id
         AND campaign.tenant_id = log.tenant_id
        WHERE activity.intervention_log_id = log.id
          AND activity.tenant_id = log.tenant_id
        """
    )

    op.create_check_constraint(
        "ck_work_activities_priority",
        "work_activities",
        "priority IN ('low', 'normal', 'high', 'urgent')",
    )
    op.create_check_constraint(
        "ck_work_activities_origin_type",
        "work_activities",
        "origin_type IN ('manual', 'campaign')",
    )
    op.create_index(
        "ix_work_activities_tenant_origin_status",
        "work_activities",
        ["tenant_id", "origin_type", "status"],
    )
    op.create_index(
        "ix_work_activities_tenant_priority_due",
        "work_activities",
        ["tenant_id", "priority", "due_at"],
    )
    op.create_index(
        "uq_work_activities_tenant_source_key",
        "work_activities",
        ["tenant_id", "source_key"],
        unique=True,
        postgresql_where=sa.text("source_key IS NOT NULL"),
    )

    # Event history is append-only; parent deletion still cascades normally.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_work_activity_event_mutation()
        RETURNS trigger AS $$
        BEGIN
            IF EXISTS (SELECT 1 FROM work_activities WHERE id = OLD.activity_id)
               AND EXISTS (SELECT 1 FROM tenants WHERE id = OLD.tenant_id)
            THEN
                RAISE EXCEPTION 'Work activity events are append-only'
                    USING ERRCODE = 'check_violation';
            END IF;
            RETURN OLD;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_work_activity_events_immutable
        BEFORE UPDATE OR DELETE ON work_activity_events
        FOR EACH ROW EXECUTE FUNCTION prevent_work_activity_event_mutation();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_work_activity_events_immutable ON work_activity_events")
    op.execute("DROP FUNCTION IF EXISTS prevent_work_activity_event_mutation()")
    op.drop_index("uq_work_activities_tenant_source_key", table_name="work_activities")
    op.drop_index("ix_work_activities_tenant_priority_due", table_name="work_activities")
    op.drop_index("ix_work_activities_tenant_origin_status", table_name="work_activities")
    op.drop_constraint("ck_work_activities_origin_type", "work_activities", type_="check")
    op.drop_constraint("ck_work_activities_priority", "work_activities", type_="check")
    op.drop_column("work_activities", "source_key")
    op.drop_column("work_activities", "campaign_id")
    op.drop_column("work_activities", "origin_type")
    op.drop_column("work_activities", "priority")
