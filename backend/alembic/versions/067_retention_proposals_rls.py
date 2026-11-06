"""Issue #178: remove public proposal access and enforce tenant RLS.

Revision ID: 067_retention_proposals_rls
Revises: 066_object_index_views
"""

from alembic import op

revision = "067_retention_proposals_rls"
down_revision = "066_object_index_views"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The authenticated MIRA backend sets app.tenant_id transaction-locally.
    # This table was created in 034 without an RLS policy, unlike its audit table.
    op.execute("ALTER TABLE public.retention_campaign_proposals ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.retention_campaign_proposals FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY retention_proposals_tenant_isolation
        ON public.retention_campaign_proposals
        FOR ALL
        USING (
            tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        )
        WITH CHECK (
            tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        )
    """)

    # The MIRA browser never reads/writes this table through Supabase Data API.
    # Protect deployments on Supabase AND plain PostgreSQL CI (where API roles
    # may not exist). RLS is defense-in-depth; no exposed API-role grants remain.
    op.execute("REVOKE ALL PRIVILEGES ON TABLE public.retention_campaign_proposals FROM PUBLIC")
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
                REVOKE ALL PRIVILEGES ON TABLE public.retention_campaign_proposals FROM anon;
            END IF;
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
                REVOKE ALL PRIVILEGES ON TABLE public.retention_campaign_proposals FROM authenticated;
            END IF;
        END;
        $$
    """)


def downgrade() -> None:
    # Do not accidentally restore public grants or remove tenant protection.
    # Recovery requires an explicitly reviewed forward security migration.
    raise RuntimeError("Issue #178 security hardening cannot be downgraded automatically")
