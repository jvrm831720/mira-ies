"""Durable SophiA sync queue, events and tenant-scoped resource snapshots.

Revision ID: 033_sophia_sync_jobs
Revises: 032_tenant_sophia_connections
"""
from alembic import op

revision = "033_sophia_sync_jobs"
down_revision = "032_tenant_sophia_connections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE sophia_sync_jobs (
            id UUID PRIMARY KEY,
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            idempotency_key VARCHAR(160) NOT NULL,
            request JSONB NOT NULL DEFAULT '{}'::jsonb,
            status VARCHAR(24) NOT NULL DEFAULT 'queued',
            attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
            max_attempts INTEGER NOT NULL DEFAULT 4 CHECK (max_attempts BETWEEN 1 AND 10),
            available_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            worker_id VARCHAR(120),
            locked_at TIMESTAMPTZ,
            heartbeat_at TIMESTAMPTZ,
            error_code VARCHAR(80),
            error_message TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            started_at TIMESTAMPTZ,
            finished_at TIMESTAMPTZ,
            CONSTRAINT uq_sophia_sync_jobs_id_tenant UNIQUE (id, tenant_id),
            CONSTRAINT uq_sophia_sync_jobs_idempotency UNIQUE (tenant_id, idempotency_key)
        )
    """)
    op.execute("CREATE INDEX ix_sophia_sync_jobs_queue ON sophia_sync_jobs (status, available_at, created_at)")
    op.execute("CREATE INDEX ix_sophia_sync_jobs_tenant_created ON sophia_sync_jobs (tenant_id, created_at)")
    op.execute("""
        CREATE UNIQUE INDEX uq_sophia_sync_jobs_one_active_per_tenant
        ON sophia_sync_jobs (tenant_id)
        WHERE status IN ('queued', 'running', 'retry_wait')
    """)
    op.execute("""
        CREATE TABLE sophia_sync_job_events (
            id UUID PRIMARY KEY,
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            job_id UUID NOT NULL,
            event_type VARCHAR(60) NOT NULL,
            details JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT fk_sophia_sync_events_job_tenant
                FOREIGN KEY (job_id, tenant_id)
                REFERENCES sophia_sync_jobs (id, tenant_id) ON DELETE CASCADE
        )
    """)
    op.execute("CREATE INDEX ix_sophia_sync_events_tenant_job ON sophia_sync_job_events (tenant_id, job_id, created_at)")
    op.execute("""
        CREATE TABLE sophia_student_resources (
            id UUID PRIMARY KEY,
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            student_id UUID NOT NULL,
            job_id UUID NOT NULL,
            resource VARCHAR(40) NOT NULL,
            source_codigo_interno INTEGER NOT NULL CHECK (source_codigo_interno > 0),
            payload JSONB NOT NULL,
            record_count INTEGER NOT NULL DEFAULT 0 CHECK (record_count >= 0),
            observed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_sophia_resource_student UNIQUE (tenant_id, student_id, resource),
            CONSTRAINT fk_sophia_resource_student_tenant
                FOREIGN KEY (tenant_id, student_id)
                REFERENCES students (tenant_id, id) ON DELETE CASCADE,
            CONSTRAINT fk_sophia_resource_job_tenant
                FOREIGN KEY (job_id, tenant_id)
                REFERENCES sophia_sync_jobs (id, tenant_id) ON DELETE CASCADE
        )
    """)
    op.execute("CREATE INDEX ix_sophia_resources_tenant_resource ON sophia_student_resources (tenant_id, resource)")
    for table in ("sophia_sync_jobs", "sophia_sync_job_events", "sophia_student_resources"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"""
            CREATE POLICY {table}_isolation ON {table}
            USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
            WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS sophia_student_resources")
    op.execute("DROP TABLE IF EXISTS sophia_sync_job_events")
    op.execute("DROP TABLE IF EXISTS sophia_sync_jobs")
