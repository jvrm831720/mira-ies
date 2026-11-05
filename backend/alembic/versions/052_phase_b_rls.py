"""Apply RLS to Phase B organization, membership and workspace tables.

Revision ID: 052_phase_b_rls
Revises: 051_organization_membership
"""
from typing import Sequence, Union

from alembic import op

revision: str = "052_phase_b_rls"
down_revision: Union[str, None] = "051_organization_membership"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    tenant_tables = (
        "mira_tenant_branding",
        "mira_tenant_domains",
        "mira_module_entitlements",
    )
    for table in tenant_tables:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_tenant_isolation ON {table} "
            "USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid) "
            "WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)"
        )

    op.execute("ALTER TABLE mira_organizations ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE mira_organizations FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY mira_organizations_tenant_isolation ON mira_organizations
        USING (
          EXISTS (
            SELECT 1 FROM tenants t
            WHERE t.organization_id = mira_organizations.id
              AND t.id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
          )
        )
        WITH CHECK (
          EXISTS (
            SELECT 1 FROM tenants t
            WHERE t.organization_id = mira_organizations.id
              AND t.id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
          )
        )
        """
    )

    op.execute("ALTER TABLE mira_memberships ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE mira_memberships FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY mira_memberships_select_scope ON mira_memberships
        FOR SELECT
        USING (
          tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
          OR user_id = NULLIF(current_setting('app.user_id', true), '')::uuid
        )
        """
    )
    op.execute(
        """
        CREATE POLICY mira_memberships_insert_scope ON mira_memberships
        FOR INSERT
        WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        """
    )
    op.execute(
        """
        CREATE POLICY mira_memberships_update_scope ON mira_memberships
        FOR UPDATE
        USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        """
    )
    op.execute(
        """
        CREATE POLICY mira_memberships_delete_scope ON mira_memberships
        FOR DELETE
        USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        """
    )

    # Recovery codes belong to the global user identity, not the legacy home tenant.
    # The app.user_id value is set only after signed-session or one-time challenge validation.
    op.execute("ALTER TABLE mira_mfa_recovery_codes FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS mira_mfa_recovery_codes_tenant_isolation ON mira_mfa_recovery_codes")
    op.execute(
        """
        CREATE POLICY mira_mfa_recovery_codes_user_scope ON mira_mfa_recovery_codes
        USING (user_id = NULLIF(current_setting('app.user_id', true), '')::uuid)
        WITH CHECK (user_id = NULLIF(current_setting('app.user_id', true), '')::uuid)
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS mira_mfa_recovery_codes_user_scope ON mira_mfa_recovery_codes")
    op.execute("ALTER TABLE mira_mfa_recovery_codes NO FORCE ROW LEVEL SECURITY")
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

    op.execute("DROP POLICY IF EXISTS mira_memberships_delete_scope ON mira_memberships")
    op.execute("DROP POLICY IF EXISTS mira_memberships_update_scope ON mira_memberships")
    op.execute("DROP POLICY IF EXISTS mira_memberships_insert_scope ON mira_memberships")
    op.execute("DROP POLICY IF EXISTS mira_memberships_select_scope ON mira_memberships")
    op.execute("DROP POLICY IF EXISTS mira_organizations_tenant_isolation ON mira_organizations")
    for table in (
        "mira_memberships",
        "mira_organizations",
        "mira_tenant_branding",
        "mira_tenant_domains",
        "mira_module_entitlements",
    ):
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
