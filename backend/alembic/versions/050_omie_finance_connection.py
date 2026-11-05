"""Tenant-scoped encrypted Omie credentials for read-only finance access.

Revision ID: 050_omie_finance_connection
Revises: 049_composio_tool_approvals
"""
from alembic import op

revision = "050_omie_finance_connection"
down_revision = "049_composio_tool_approvals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE tenant_omie_connections (
            id UUID PRIMARY KEY,
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            app_hash VARCHAR(160) NOT NULL,
            encrypted_access_token TEXT NOT NULL,
            encrypted_refresh_token TEXT NOT NULL,
            token_expires_at TIMESTAMPTZ NOT NULL,
            is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
            status VARCHAR(24) NOT NULL DEFAULT 'configured'
                CHECK (status IN ('configured', 'connected', 'error', 'disabled')),
            last_tested_at TIMESTAMPTZ NULL,
            last_error_code VARCHAR(40) NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_tenant_omie_connections_tenant UNIQUE (tenant_id)
        )
    """)
    op.execute("CREATE INDEX ix_tenant_omie_connections_enabled ON tenant_omie_connections (tenant_id, is_enabled)")
    op.execute("ALTER TABLE tenant_omie_connections ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE tenant_omie_connections FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_omie_connections_isolation
        ON tenant_omie_connections
        USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS tenant_omie_connections")
