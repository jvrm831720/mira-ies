"""Persist tenant-scoped TOTVS RM snapshot runs, pages and records.

Revision ID: 029_rm_snapshot_persistence
Revises: 028_tenant_sponte_connections
"""
from alembic import op

revision = "029_rm_snapshot_persistence"
down_revision = "028_tenant_sponte_connections"
branch_labels = None
depends_on = None

def upgrade() -> None:
 op.execute("""
 CREATE TABLE rm_sync_scopes (
 id UUID PRIMARY KEY,
 tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
 coligada_id VARCHAR(80) NOT NULL,
 source_name VARCHAR(120) NOT NULL,
 entity_name VARCHAR(120) NOT NULL,
 schema_version VARCHAR(40) NOT NULL,
 current_snapshot_run_id UUID NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 CONSTRAINT uq_rm_sync_scopes_identity
 UNIQUE (tenant_id, coligada_id, source_name, entity_name, schema_version),
 CONSTRAINT uq_rm_sync_scopes_id_tenant UNIQUE (id, tenant_id)
 )
 """)
 op.execute("""
 CREATE TABLE rm_sync_runs (
 id UUID PRIMARY KEY,
 scope_id UUID NOT NULL,
 tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
 identity_fields JSONB NOT NULL,
 coligada_field VARCHAR(80) NOT NULL,
 deletion_semantics_confirmed BOOLEAN NOT NULL DEFAULT FALSE,
 status VARCHAR(20) NOT NULL DEFAULT 'staging',
 next_offset INTEGER NOT NULL DEFAULT 0 CHECK (next_offset >= 0),
 record_count INTEGER NOT NULL DEFAULT 0 CHECK (record_count >= 0),
 source_complete BOOLEAN NOT NULL DEFAULT FALSE,
 expected_record_count INTEGER NULL CHECK (expected_record_count IS NULL OR expected_record_count >= 0),
 diff JSONB NULL,
 started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 committed_at TIMESTAMPTZ NULL,
 error TEXT NULL,
 CONSTRAINT uq_rm_sync_runs_id_tenant UNIQUE (id, tenant_id),
 CONSTRAINT fk_rm_sync_runs_scope_tenant
 FOREIGN KEY (scope_id, tenant_id)
 REFERENCES rm_sync_scopes(id, tenant_id) ON DELETE CASCADE,
 CONSTRAINT ck_rm_sync_runs_status
 CHECK (status IN ('staging', 'committed', 'superseded', 'failed'))
 )
 """)
 op.execute("""
 ALTER TABLE rm_sync_scopes
 ADD CONSTRAINT fk_rm_sync_scopes_current_run_tenant
 FOREIGN KEY (current_snapshot_run_id, tenant_id)
 REFERENCES rm_sync_runs(id, tenant_id)
 DEFERRABLE INITIALLY DEFERRED
 """)
 op.execute("""
 CREATE TABLE rm_sync_pages (
 id UUID PRIMARY KEY,
 run_id UUID NOT NULL,
 tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
 "offset" INTEGER NOT NULL CHECK ("offset" >= 0),
 next_offset INTEGER NOT NULL CHECK (next_offset >= "offset"),
 fingerprint VARCHAR(64) NOT NULL,
 record_count INTEGER NOT NULL CHECK (record_count >= 0),
 has_more BOOLEAN NOT NULL,
 records JSONB NOT NULL,
 CONSTRAINT uq_rm_sync_pages_run_offset UNIQUE (run_id, "offset"),
 CONSTRAINT fk_rm_sync_pages_run_tenant
 FOREIGN KEY (run_id, tenant_id)
 REFERENCES rm_sync_runs(id, tenant_id) ON DELETE CASCADE
 )
 """)
 op.execute("""
 CREATE TABLE rm_sync_records (
 id UUID PRIMARY KEY,
 run_id UUID NOT NULL,
 tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
 identity_key TEXT NOT NULL,
 payload JSONB NOT NULL,
 CONSTRAINT uq_rm_sync_records_run_identity UNIQUE (run_id, identity_key),
 CONSTRAINT fk_rm_sync_records_run_tenant
 FOREIGN KEY (run_id, tenant_id)
 REFERENCES rm_sync_runs(id, tenant_id) ON DELETE CASCADE
 )
 """)
 for table in ("rm_sync_scopes", "rm_sync_runs", "rm_sync_pages", "rm_sync_records"):
 op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
 op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
 op.execute(f"""
 CREATE POLICY {table}_tenant_isolation ON {table}
 USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
 WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
 """)
 op.execute("CREATE INDEX ix_rm_sync_scopes_tenant_id ON rm_sync_scopes (tenant_id)")
 op.execute("CREATE INDEX ix_rm_sync_runs_tenant_id ON rm_sync_runs (tenant_id)")
 op.execute("CREATE INDEX ix_rm_sync_pages_tenant_id ON rm_sync_pages (tenant_id)")
 op.execute("CREATE INDEX ix_rm_sync_records_tenant_id ON rm_sync_records (tenant_id)")
 op.execute("CREATE INDEX ix_rm_sync_runs_scope_status ON rm_sync_runs (scope_id, status)")
 op.execute("CREATE INDEX ix_rm_sync_runs_tenant_started ON rm_sync_runs (tenant_id, started_at DESC)")
 op.execute('CREATE INDEX ix_rm_sync_pages_tenant_run ON rm_sync_pages (tenant_id, run_id, "offset")')
 op.execute("CREATE INDEX ix_rm_sync_records_tenant_run ON rm_sync_records (tenant_id, run_id)")

def downgrade() -> None:
 op.execute("DROP TABLE IF EXISTS rm_sync_records")
 op.execute("DROP TABLE IF EXISTS rm_sync_pages")
 op.execute("ALTER TABLE IF EXISTS rm_sync_scopes DROP CONSTRAINT IF EXISTS fk_rm_sync_scopes_current_run_tenant")
 op.execute("DROP TABLE IF EXISTS rm_sync_runs")
 op.execute("DROP TABLE IF EXISTS rm_sync_scopes")
