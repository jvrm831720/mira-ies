"""Store tenant ownership directly on MFA recovery codes for reliable RLS.

Revision ID: 026_mfa_recovery_tenant_rls
Revises: 025_mfa_fk_indexes
"""
from alembic import op

revision = "026_mfa_recovery_tenant_rls"
down_revision = "025_mfa_fk_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE mira_mfa_recovery_codes "
        "ADD COLUMN IF NOT EXISTS tenant_id UUID"
    )
    op.execute(
        """
        UPDATE mira_mfa_recovery_codes AS recovery
        SET tenant_id = users.tenant_id
        FROM mira_users AS users
        WHERE recovery.user_id = users.id
          AND recovery.tenant_id IS NULL
        """
    )
    op.execute(
        "ALTER TABLE mira_mfa_recovery_codes ALTER COLUMN tenant_id SET NOT NULL"
    )
    op.execute(
        """
        DO $$ BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'mira_mfa_recovery_codes_tenant_id_fkey'
              AND conrelid = 'mira_mfa_recovery_codes'::regclass
          ) THEN
            ALTER TABLE mira_mfa_recovery_codes
              ADD CONSTRAINT mira_mfa_recovery_codes_tenant_id_fkey
              FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
          END IF;
        END $$;
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_mira_mfa_recovery_codes_tenant_id "
        "ON mira_mfa_recovery_codes (tenant_id)"
    )
    op.execute(
        "DROP POLICY IF EXISTS mira_mfa_recovery_codes_tenant_isolation "
        "ON mira_mfa_recovery_codes"
    )
    op.execute(
        """
        CREATE POLICY mira_mfa_recovery_codes_tenant_isolation
        ON mira_mfa_recovery_codes
        USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS mira_mfa_recovery_codes_tenant_isolation "
        "ON mira_mfa_recovery_codes"
    )
    op.execute("DROP INDEX IF EXISTS ix_mira_mfa_recovery_codes_tenant_id")
    op.execute(
        "ALTER TABLE mira_mfa_recovery_codes "
        "DROP CONSTRAINT IF EXISTS mira_mfa_recovery_codes_tenant_id_fkey"
    )
    op.execute("ALTER TABLE mira_mfa_recovery_codes DROP COLUMN IF EXISTS tenant_id")
    op.execute(
        """
        CREATE POLICY mira_mfa_recovery_codes_tenant_isolation
        ON mira_mfa_recovery_codes
        USING (
          user_id IN (
            SELECT id FROM mira_users
            WHERE tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
          )
        )
        WITH CHECK (
          user_id IN (
            SELECT id FROM mira_users
            WHERE tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
          )
        )
        """
    )
