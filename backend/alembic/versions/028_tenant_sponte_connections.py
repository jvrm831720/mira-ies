"""Tenant-scoped encrypted Sponte BI connection and per-endpoint watermarks.

Revision ID: 028_tenant_sponte_connections
Revises: 027_tenant_jacad_connections
"""
from alembic import op

revision = "028_tenant_sponte_connections"
down_revision = "027_tenant_jacad_connections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE tenant_sponte_connections (
            id UUID PRIMARY KEY,
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            encrypted_api_key TEXT NOT NULL,
            client_code INTEGER NOT NULL,
            initial_extraction_date DATE NOT NULL DEFAULT DATE '2025-01-01',
            sync_watermarks JSONB NOT NULL DEFAULT '{}'::jsonb,
            is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
            status VARCHAR(24) NOT NULL DEFAULT 'configured',
            last_tested_at TIMESTAMPTZ NULL,
            last_sync_at TIMESTAMPTZ NULL,
            last_sync_status VARCHAR(24) NULL,
            last_sync_records INTEGER NOT NULL DEFAULT 0,
            last_error TEXT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_tenant_sponte_connections_tenant UNIQUE (tenant_id)
        )
    """)
    op.execute("CREATE INDEX ix_tenant_sponte_connections_tenant_id ON tenant_sponte_connections (tenant_id)")
    op.execute("ALTER TABLE tenant_sponte_connections ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE tenant_sponte_connections FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_sponte_connections_isolation
        ON tenant_sponte_connections
        USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS tenant_sponte_connections")
