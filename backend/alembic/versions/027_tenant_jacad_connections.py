"""Tenant-scoped encrypted JACAD connection configuration.

Revision ID: 027_tenant_jacad_connections
Revises: 026_mfa_recovery_tenant_rls
"""
from alembic import op

revision = "027_tenant_jacad_connections"
down_revision = "026_mfa_recovery_tenant_rls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE tenant_jacad_connections (
            id UUID PRIMARY KEY,
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            base_url VARCHAR(255) NOT NULL,
            encrypted_api_token TEXT NOT NULL,
            default_org_id INTEGER NULL,
            is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
            status VARCHAR(24) NOT NULL DEFAULT 'configured',
            last_tested_at TIMESTAMPTZ NULL,
            last_sync_at TIMESTAMPTZ NULL,
            last_sync_status VARCHAR(24) NULL,
            last_sync_records INTEGER NOT NULL DEFAULT 0,
            last_error TEXT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_tenant_jacad_connections_tenant UNIQUE (tenant_id)
        )
    """)
    op.execute("CREATE INDEX ix_tenant_jacad_connections_tenant_id ON tenant_jacad_connections (tenant_id)")
    op.execute("ALTER TABLE tenant_jacad_connections ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE tenant_jacad_connections FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_jacad_connections_isolation
        ON tenant_jacad_connections
        USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS tenant_jacad_connections")
