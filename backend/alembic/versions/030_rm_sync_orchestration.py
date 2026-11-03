"""Durable queue and audit events for TOTVS RM synchronization.

Revision ID: 030_rm_sync_orchestration
Revises: 029_rm_snapshot_persistence
"""
from alembic import op

revision = "030_rm_sync_orchestration"
down_revision = "029_rm_snapshot_persistence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE rm_sync_jobs (
            id UUID PRIMARY KEY,
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            scope_id UUID NOT NULL,
            coligada_id VARCHAR(80) NOT NULL,
            snapshot_run_id UUID NULL,
            idempotency_key VARCHAR(160) NOT NULL,
            request JSONB NOT NULL DEFAULT '{}'::jsonb,
            status VARCHAR(24) NOT NULL DEFAULT 'queued',
            attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
            max_attempts INTEGER NOT NULL DEFAULT 5 CHECK (max_attempts BETWEEN 1 AND 12),
            available_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            worker_id VARCHAR(120) NULL,
            locked_at TIMESTAMPTZ NULL,
            heartbeat_at TIMESTAMPTZ NULL,
            cancel_requested_at TIMESTAMPTZ NULL,
            error_code VARCHAR(80) NULL,
            error_message TEXT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            started_at TIMESTAMPTZ NULL,
            finished_at TIMESTAMPTZ NULL,
            CONSTRAINT uq_rm_sync_jobs_id_tenant UNIQUE (id, tenant_id),
            CONSTRAINT uq_rm_sync_jobs_tenant_idempotency UNIQUE (tenant_id, idempotency_key),
            CONSTRAINT fk_rm_sync_jobs_scope_tenant
              FOREIGN KEY (scope_id, tenant_id)
              REFERENCES rm_sync_scopes(id, tenant_id) ON DELETE CASCADE,
            CONSTRAINT fk_rm_sync_jobs_snapshot_tenant
              FOREIGN KEY (snapshot_run_id, tenant_id)
              REFERENCES rm_sync_runs(id, tenant_id),
            CONSTRAINT ck_rm_sync_jobs_status
              CHECK (status IN ('queued','running','retry_wait','cancel_requested','cancelled','succeeded','failed'))
        )
    """)
    op.execute("""
        CREATE UNIQUE INDEX uq_rm_sync_jobs_active_coligada
        ON rm_sync_jobs(tenant_id, coligada_id)
        WHERE status IN ('queued','running','retry_wait','cancel_requested')
    """)
    op.execute("CREATE INDEX ix_rm_sync_jobs_queue ON rm_sync_jobs(status, available_at, created_at)")
    op.execute("CREATE INDEX ix_rm_sync_jobs_tenant_created ON rm_sync_jobs(tenant_id, created_at DESC)")
    op.execute("CREATE INDEX ix_rm_sync_jobs_scope_status ON rm_sync_jobs(scope_id, status)")
    op.execute("""
        CREATE TABLE rm_sync_job_events (
            id UUID PRIMARY KEY,
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            job_id UUID NOT NULL,
            event_type VARCHAR(60) NOT NULL,
            severity VARCHAR(12) NOT NULL DEFAULT 'info',
            details JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT fk_rm_sync_job_events_job_tenant
              FOREIGN KEY (job_id, tenant_id)
              REFERENCES rm_sync_jobs(id, tenant_id) ON DELETE CASCADE
        )
    """)
    op.execute("CREATE INDEX ix_rm_sync_job_events_tenant_job ON rm_sync_job_events(tenant_id, job_id, created_at)")
    for table in ("rm_sync_jobs", "rm_sync_job_events"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"""
            CREATE POLICY {table}_tenant_isolation ON {table}
            USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
            WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS rm_sync_job_events")
    op.execute("DROP INDEX IF EXISTS uq_rm_sync_jobs_active_coligada")
    op.execute("DROP TABLE IF EXISTS rm_sync_jobs")
