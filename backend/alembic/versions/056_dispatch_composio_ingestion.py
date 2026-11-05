"""Encrypted, tenant-isolated Composio read-tool observations for MIRA Dispatch.

Revision ID: 056_dispatch_composio_ingestion
Revises: 055_dispatch_platform
"""
from alembic import op

revision = "056_dispatch_composio_ingestion"
down_revision = "055_dispatch_platform"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE dispatch_source_observations (
            id UUID PRIMARY KEY,
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            connected_account_id VARCHAR(120) NOT NULL,
            toolkit_slug VARCHAR(80) NOT NULL,
            tool_slug VARCHAR(120) NOT NULL,
            source_record_id VARCHAR(160) NOT NULL,
            subject_type VARCHAR(20) NOT NULL CHECK (subject_type IN ('student','external')),
            subject_ref VARCHAR(160) NOT NULL,
            record_type VARCHAR(20) NOT NULL
                CHECK (record_type IN ('contact','obligation','generic')),
            payload_ciphertext TEXT NOT NULL,
            payload_hash VARCHAR(64) NOT NULL,
            source_version BIGINT NOT NULL DEFAULT 1,
            observed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (tenant_id, connected_account_id, tool_slug, source_record_id),
            FOREIGN KEY (tenant_id,connected_account_id)
                REFERENCES tenant_composio_accounts(tenant_id,connected_account_id)
                ON DELETE CASCADE
        )
    """)
    op.execute("""
        CREATE INDEX ix_dispatch_source_observations_audience
        ON dispatch_source_observations
          (tenant_id,connected_account_id,tool_slug,subject_type,subject_ref)
    """)
    op.execute("""
        CREATE TABLE dispatch_source_import_runs (
            id UUID PRIMARY KEY,
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            connected_account_id VARCHAR(120) NOT NULL,
            toolkit_slug VARCHAR(80) NOT NULL,
            tool_slug VARCHAR(120) NOT NULL,
            actor_id UUID NOT NULL REFERENCES mira_users(id),
            idempotency_key VARCHAR(120) NOT NULL,
            request_hash VARCHAR(64) NOT NULL,
            status VARCHAR(20) NOT NULL CHECK (status IN ('running','succeeded','failed','unknown')),
            rows_total INTEGER NOT NULL DEFAULT 0,
            rows_created INTEGER NOT NULL DEFAULT 0,
            rows_updated INTEGER NOT NULL DEFAULT 0,
            error_code VARCHAR(80),
            started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            finished_at TIMESTAMPTZ,
            UNIQUE (tenant_id,idempotency_key),
            FOREIGN KEY (tenant_id,connected_account_id)
                REFERENCES tenant_composio_accounts(tenant_id,connected_account_id)
                ON DELETE CASCADE
        )
    """)
    for table in ("dispatch_source_observations", "dispatch_source_import_runs"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"""
            CREATE POLICY {table}_tenant_isolation ON {table}
            USING (tenant_id = NULLIF(current_setting('app.tenant_id',true),'')::uuid)
            WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id',true),'')::uuid)
        """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS dispatch_source_import_runs")
    op.execute("DROP TABLE IF EXISTS dispatch_source_observations")
