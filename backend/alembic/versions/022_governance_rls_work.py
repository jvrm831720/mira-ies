"""Normalize governance RLS and operational work-domain constraints.

Revision ID: 022_governance_rls_work
Revises: 021_work_activities
"""
from alembic import op

revision = "022_governance_rls_work"
down_revision = "021_work_activities"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Both governance tables are tenant-owned. Keep administrative reads
    # available to the database owner, while blocking direct anon/authenticated
    # access unless the application has set app.tenant_id.
    op.execute("ALTER TABLE tenant_data_use_policies ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE institutional_training_authorizations ENABLE ROW LEVEL SECURITY")

    op.execute("DROP POLICY IF EXISTS tenant_data_use_policies_tenant_isolation ON tenant_data_use_policies")
    op.execute(
        """
        CREATE POLICY tenant_data_use_policies_tenant_isolation
        ON tenant_data_use_policies
        USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        """
    )
    op.execute(
        "DROP POLICY IF EXISTS institutional_training_authorizations_tenant_isolation "
        "ON institutional_training_authorizations"
    )
    op.execute(
        """
        CREATE POLICY institutional_training_authorizations_tenant_isolation
        ON institutional_training_authorizations
        USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        """
    )

    # Keep the API's finite state machine enforceable for direct SQL writes too.
    op.execute(
        """
        DO $$ BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'ck_work_activities_activity_type'
              AND conrelid = 'work_activities'::regclass
          ) THEN
            ALTER TABLE work_activities
              ADD CONSTRAINT ck_work_activities_activity_type
              CHECK (activity_type IN ('follow_up', 'contact', 'review', 'other'));
          END IF;
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'ck_work_activities_status'
              AND conrelid = 'work_activities'::regclass
          ) THEN
            ALTER TABLE work_activities
              ADD CONSTRAINT ck_work_activities_status
              CHECK (status IN ('open', 'in_progress', 'completed', 'cancelled'));
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE institutional_training_authorizations NO FORCE ROW LEVEL SECURITY")
    op.execute(
        "DROP POLICY IF EXISTS institutional_training_authorizations_tenant_isolation "
        "ON institutional_training_authorizations"
    )
    op.execute("ALTER TABLE institutional_training_authorizations DISABLE ROW LEVEL SECURITY")

    op.execute("DROP POLICY IF EXISTS tenant_data_use_policies_tenant_isolation ON tenant_data_use_policies")
    op.execute("ALTER TABLE tenant_data_use_policies DISABLE ROW LEVEL SECURITY")

    op.execute("ALTER TABLE work_activities DROP CONSTRAINT IF EXISTS ck_work_activities_status")
    op.execute("ALTER TABLE work_activities DROP CONSTRAINT IF EXISTS ck_work_activities_activity_type")
