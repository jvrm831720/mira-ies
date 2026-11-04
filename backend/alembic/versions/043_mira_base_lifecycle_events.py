"""Append-only lifecycle events for global MIRA Base activation.

Revision ID: 043_mira_base_lifecycle_events
Revises: 042_training_runs_snapshots
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "043_mira_base_lifecycle_events"
down_revision = "042_training_runs_snapshots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mira_base_lifecycle_events",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("artifact_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("model_artifacts.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("training_runs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("from_status", sa.String(20), nullable=True),
        sa.Column("to_status", sa.String(20), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("actor_admin_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("mira_control_admins.id", ondelete="SET NULL"), nullable=True),
        sa.Column("rollback_of_artifact_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("model_artifacts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("metadata_redacted", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "event_type IN ('register_candidate', 'approve', 'reject', 'activate', 'retire', 'rollback')",
            name="ck_mira_base_lifecycle_event_type",
        ),
        sa.CheckConstraint(
            "to_status IN ('candidate', 'approved', 'active', 'retired', 'rejected')",
            name="ck_mira_base_lifecycle_to_status",
        ),
    )
    op.create_index("ix_mira_base_lifecycle_events_artifact", "mira_base_lifecycle_events", ["artifact_id", "created_at"])
    op.create_index("ix_mira_base_lifecycle_events_type", "mira_base_lifecycle_events", ["event_type", "created_at"])
    op.execute("ALTER TABLE mira_base_lifecycle_events ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE mira_base_lifecycle_events FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY mira_base_lifecycle_events_admin ON mira_base_lifecycle_events
        FOR ALL
        USING (current_setting('app.is_mira_admin', true) = 'true')
        WITH CHECK (current_setting('app.is_mira_admin', true) = 'true')
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION reject_mira_base_lifecycle_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $life$
        BEGIN
            IF pg_trigger_depth() > 1 THEN
                IF TG_OP = 'DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
            END IF;
            RAISE EXCEPTION 'mira_base_lifecycle_events history is append-only';
        END;
        $life$
        """
    )
    op.execute(
        "CREATE TRIGGER trg_mira_base_lifecycle_append_only "
        "BEFORE UPDATE OR DELETE ON mira_base_lifecycle_events "
        "FOR EACH ROW EXECUTE FUNCTION reject_mira_base_lifecycle_mutation()"
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_model_artifacts_one_active_base
        ON model_artifacts ((1))
        WHERE tenant_id IS NULL AND scope = 'base' AND is_active = true
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_model_artifacts_one_active_base")
    op.execute("DROP TRIGGER IF EXISTS trg_mira_base_lifecycle_append_only ON mira_base_lifecycle_events")
    op.execute("DROP FUNCTION IF EXISTS reject_mira_base_lifecycle_mutation()")
    op.execute("DROP POLICY IF EXISTS mira_base_lifecycle_events_admin ON mira_base_lifecycle_events")
    op.execute("ALTER TABLE mira_base_lifecycle_events NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE mira_base_lifecycle_events DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_mira_base_lifecycle_events_type", table_name="mira_base_lifecycle_events")
    op.drop_index("ix_mira_base_lifecycle_events_artifact", table_name="mira_base_lifecycle_events")
    op.drop_table("mira_base_lifecycle_events")
