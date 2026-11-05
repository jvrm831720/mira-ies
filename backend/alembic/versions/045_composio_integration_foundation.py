"""Tenant-scoped Composio references and tool audit foundation.

Revision ID: 045_composio_foundation
Revises: 044_tenant_conn_dest
"""
from alembic import op

revision = "045_composio_foundation"
down_revision = "044_tenant_conn_dest"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE tenant_composio_sessions (
            id UUID PRIMARY KEY,
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            composio_user_id VARCHAR(80) NOT NULL UNIQUE,
            session_id VARCHAR(120) NULL,
            status VARCHAR(16) NOT NULL DEFAULT 'provisioned'
                CHECK (status IN ('provisioned', 'active', 'disabled')),
            created_by_user_id UUID NULL REFERENCES mira_users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_tenant_composio_sessions_tenant UNIQUE (tenant_id)
        )
    """)
    op.execute("""
        CREATE TABLE tenant_composio_accounts (
            id UUID PRIMARY KEY,
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            toolkit_slug VARCHAR(80) NOT NULL,
            connected_account_id VARCHAR(120) NOT NULL UNIQUE,
            auth_config_id VARCHAR(80) NULL,
            display_name VARCHAR(160) NULL,
            status VARCHAR(16) NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'expired', 'revoked', 'error')),
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            connected_by_user_id UUID NULL REFERENCES mira_users(id) ON DELETE SET NULL,
            connected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            disconnected_at TIMESTAMPTZ NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_tenant_composio_account
                UNIQUE (tenant_id, toolkit_slug, connected_account_id)
        )
    """)
    op.execute("""
        CREATE TABLE tenant_composio_tool_audit (
            id UUID PRIMARY KEY,
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            actor_user_id UUID NULL REFERENCES mira_users(id) ON DELETE SET NULL,
            connected_account_id VARCHAR(120) NULL,
            toolkit_slug VARCHAR(80) NOT NULL,
            tool_slug VARCHAR(120) NOT NULL,
            execution_id VARCHAR(120) NULL,
            status VARCHAR(24) NOT NULL CHECK (
                status IN ('requested', 'succeeded', 'failed', 'denied', 'pending_approval')
            ),
            approval_required BOOLEAN NOT NULL DEFAULT FALSE,
            approval_status VARCHAR(24) NULL,
            request_fingerprint VARCHAR(64) NULL,
            duration_ms INTEGER NULL CHECK (duration_ms IS NULL OR duration_ms >= 0),
            error_code VARCHAR(80) NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX ix_tenant_composio_accounts_tenant_toolkit ON tenant_composio_accounts (tenant_id, toolkit_slug, status)")
    op.execute("CREATE INDEX ix_tenant_composio_tool_audit_tenant_created ON tenant_composio_tool_audit (tenant_id, created_at)")
    op.execute("CREATE INDEX ix_tenant_composio_tool_audit_execution ON tenant_composio_tool_audit (execution_id)")
    for table in (
        "tenant_composio_sessions",
        "tenant_composio_accounts",
        "tenant_composio_tool_audit",
    ):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"""
            CREATE POLICY {table}_isolation ON {table}
            USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
            WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        """)
    op.execute("""
        CREATE FUNCTION reject_composio_audit_mutation()
        RETURNS trigger LANGUAGE plpgsql
        AS 'BEGIN RAISE EXCEPTION ''Composio tool audit is append-only''; END;'
    """)
    op.execute("""
        CREATE TRIGGER tenant_composio_tool_audit_append_only
        BEFORE UPDATE OR DELETE ON tenant_composio_tool_audit
        FOR EACH ROW EXECUTE FUNCTION reject_composio_audit_mutation()
    """)
    op.execute("""
        CREATE TRIGGER tenant_composio_tool_audit_no_truncate
        BEFORE TRUNCATE ON tenant_composio_tool_audit
        FOR EACH STATEMENT EXECUTE FUNCTION reject_composio_audit_mutation()
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS tenant_composio_tool_audit")
    op.execute("DROP FUNCTION IF EXISTS reject_composio_audit_mutation()")
    op.execute("DROP TABLE IF EXISTS tenant_composio_accounts")
    op.execute("DROP TABLE IF EXISTS tenant_composio_sessions")
