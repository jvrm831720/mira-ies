"""Tenant-scoped SophiA credentials and explicit student identity links.

Revision ID: 032_tenant_sophia_connections
Revises: 031_rm_sync_publish_boundary
"""
from alembic import op

revision = "032_tenant_sophia_connections"
down_revision = "031_rm_sync_publish_boundary"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE tenant_sophia_connections (
            id UUID PRIMARY KEY,
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            base_url VARCHAR(500) NOT NULL,
            encrypted_username TEXT NOT NULL,
            encrypted_password TEXT NOT NULL,
            is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
            status VARCHAR(24) NOT NULL DEFAULT 'configured',
            last_tested_at TIMESTAMPTZ NULL,
            last_error TEXT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_tenant_sophia_connections_tenant UNIQUE (tenant_id)
        )
    """)
    op.execute("CREATE INDEX ix_tenant_sophia_connections_tenant_id ON tenant_sophia_connections (tenant_id)")
    op.execute("""
        CREATE TABLE tenant_sophia_student_links (
            id UUID PRIMARY KEY,
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            student_id UUID NOT NULL,
            codigo_interno INTEGER NOT NULL CHECK (codigo_interno > 0),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            created_by_user_id UUID NULL REFERENCES mira_users(id) ON DELETE SET NULL,
            CONSTRAINT uq_tenant_sophia_student_links_student UNIQUE (tenant_id, student_id),
            CONSTRAINT uq_tenant_sophia_student_links_codigo UNIQUE (tenant_id, codigo_interno),
            CONSTRAINT fk_tenant_sophia_student_links_student_tenant
                FOREIGN KEY (tenant_id, student_id)
                REFERENCES students (tenant_id, id) ON DELETE CASCADE
        )
    """)
    op.execute("CREATE INDEX ix_tenant_sophia_student_links_tenant_id ON tenant_sophia_student_links (tenant_id)")
    for table in ("tenant_sophia_connections", "tenant_sophia_student_links"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"""
            CREATE POLICY {table}_isolation ON {table}
            USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
            WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS tenant_sophia_student_links")
    op.execute("DROP TABLE IF EXISTS tenant_sophia_connections")
