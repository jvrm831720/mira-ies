"""Training runs and immutable dataset snapshots for shared/base training.

Revision ID: 042_training_runs_snapshots
Revises: 041_eligible_contributions
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "042_training_runs_snapshots"
down_revision = "041_eligible_contributions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "training_dataset_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("scope", sa.String(20), nullable=False),
        sa.Column("dataset_hash", sa.String(128), nullable=False),
        sa.Column("contribution_hashes", postgresql.JSONB(), nullable=False),
        sa.Column("tenant_ids", postgresql.JSONB(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("anonymization_rules_version", sa.String(40), nullable=False),
        sa.Column("feature_schema_version", sa.String(40), nullable=False),
        sa.Column("built_by_admin_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("mira_control_admins.id", ondelete="SET NULL"), nullable=True),
        sa.Column("built_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("scope IN ('shared_base', 'institutional')", name="ck_training_dataset_snapshots_scope"),
        sa.UniqueConstraint("dataset_hash", name="uq_training_dataset_snapshots_hash"),
    )
    op.create_index("ix_training_dataset_snapshots_scope_built", "training_dataset_snapshots", ["scope", "built_at"])

    op.create_table(
        "training_runs",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("run_key", sa.String(80), nullable=False),
        sa.Column("scope", sa.String(20), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("training_dataset_snapshots.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("dataset_hash", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("triggered_by_admin_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("mira_control_admins.id", ondelete="SET NULL"), nullable=True),
        sa.Column("artifact_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("model_artifacts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("metrics", postgresql.JSONB(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("scope IN ('shared_base', 'institutional')", name="ck_training_runs_scope"),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')",
            name="ck_training_runs_status",
        ),
        sa.UniqueConstraint("run_key", name="uq_training_runs_run_key"),
    )
    op.create_index("ix_training_runs_scope_status", "training_runs", ["scope", "status"])
    op.create_index("ix_training_runs_tenant_created", "training_runs", ["tenant_id", "created_at"])
    op.create_index("ix_training_runs_snapshot", "training_runs", ["snapshot_id"])

    # Snapshots are immutable evidence
    for table in ("training_dataset_snapshots", "training_runs"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")

    # Snapshots: global shared evidence readable only by mira admin context
    op.execute(
        """
        CREATE POLICY training_dataset_snapshots_admin ON training_dataset_snapshots
        FOR ALL
        USING (current_setting('app.is_mira_admin', true) = 'true')
        WITH CHECK (current_setting('app.is_mira_admin', true) = 'true')
        """
    )

    # Runs: institutional runs visible to tenant or admin; shared_base only admin
    op.execute(
        """
        CREATE POLICY training_runs_isolation ON training_runs
        FOR ALL
        USING (
            current_setting('app.is_mira_admin', true) = 'true'
            OR (
                tenant_id IS NOT NULL
                AND tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
            )
        )
        WITH CHECK (
            current_setting('app.is_mira_admin', true) = 'true'
            OR (
                tenant_id IS NOT NULL
                AND tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
            )
        )
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION reject_training_snapshot_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $snap$
        BEGIN
            IF pg_trigger_depth() > 1 THEN
                IF TG_OP = 'DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
            END IF;
            RAISE EXCEPTION 'training_dataset_snapshots are immutable';
        END;
        $snap$
        """
    )
    op.execute(
        "CREATE TRIGGER trg_training_dataset_snapshots_immutable "
        "BEFORE UPDATE OR DELETE ON training_dataset_snapshots "
        "FOR EACH ROW EXECUTE FUNCTION reject_training_snapshot_mutation()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_training_dataset_snapshots_immutable ON training_dataset_snapshots")
    op.execute("DROP FUNCTION IF EXISTS reject_training_snapshot_mutation()")
    op.execute("DROP POLICY IF EXISTS training_runs_isolation ON training_runs")
    op.execute("DROP POLICY IF EXISTS training_dataset_snapshots_admin ON training_dataset_snapshots")
    for table in ("training_runs", "training_dataset_snapshots"):
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_training_runs_snapshot", table_name="training_runs")
    op.drop_index("ix_training_runs_tenant_created", table_name="training_runs")
    op.drop_index("ix_training_runs_scope_status", table_name="training_runs")
    op.drop_table("training_runs")
    op.drop_index("ix_training_dataset_snapshots_scope_built", table_name="training_dataset_snapshots")
    op.drop_table("training_dataset_snapshots")
