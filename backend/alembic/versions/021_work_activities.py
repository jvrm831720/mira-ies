"""Operational work activities for Central de Trabalho.

Revision ID: 021_work_activities
Revises: 020_risk_assessment_score_basis
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "021_work_activities"
down_revision = "020_risk_assessment_score_basis"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "work_activities",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("student_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("students.id", ondelete="SET NULL"), nullable=True),
        sa.Column("intervention_log_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("intervention_logs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("activity_type", sa.String(length=40), nullable=False, server_default="follow_up"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="open"),
        sa.Column("assignee_user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("mira_users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("mira_users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_work_activities_tenant_status", "work_activities", ["tenant_id", "status"])
    op.create_index("ix_work_activities_tenant_assignee", "work_activities", ["tenant_id", "assignee_user_id"])
    op.create_index("ix_work_activities_tenant_due", "work_activities", ["tenant_id", "due_at"])
    op.create_index("ix_work_activities_tenant_student", "work_activities", ["tenant_id", "student_id"])

    op.create_table(
        "work_activity_events",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("activity_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("work_activities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("mira_users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_work_activity_events_tenant_activity",
        "work_activity_events",
        ["tenant_id", "activity_id", "created_at"],
    )

    # RLS tenant isolation (same pattern as other tenant tables when enabled)
    op.execute("ALTER TABLE work_activities ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        DO $$ BEGIN
          CREATE POLICY work_activities_tenant_isolation ON work_activities
            USING (tenant_id::text = current_setting('app.tenant_id', true))
            WITH CHECK (tenant_id::text = current_setting('app.tenant_id', true));
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
        """
    )
    op.execute("ALTER TABLE work_activities FORCE ROW LEVEL SECURITY")

    op.execute("ALTER TABLE work_activity_events ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        DO $$ BEGIN
          CREATE POLICY work_activity_events_tenant_isolation ON work_activity_events
            USING (tenant_id::text = current_setting('app.tenant_id', true))
            WITH CHECK (tenant_id::text = current_setting('app.tenant_id', true));
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
        """
    )
    op.execute("ALTER TABLE work_activity_events FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.execute("ALTER TABLE work_activity_events NO FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS work_activity_events_tenant_isolation ON work_activity_events")
    op.execute("ALTER TABLE work_activity_events DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_work_activity_events_tenant_activity", table_name="work_activity_events")
    op.drop_table("work_activity_events")

    op.execute("ALTER TABLE work_activities NO FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS work_activities_tenant_isolation ON work_activities")
    op.execute("ALTER TABLE work_activities DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_work_activities_tenant_student", table_name="work_activities")
    op.drop_index("ix_work_activities_tenant_due", table_name="work_activities")
    op.drop_index("ix_work_activities_tenant_assignee", table_name="work_activities")
    op.drop_index("ix_work_activities_tenant_status", table_name="work_activities")
    op.drop_table("work_activities")
