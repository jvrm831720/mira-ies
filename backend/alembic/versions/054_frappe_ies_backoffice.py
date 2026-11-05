"""Optional tenant-scoped Frappe Education bridge; no operational writes.

Revision ID: 054_frappe_ies_bridge
Revises: 053_merge_heads
"""
from alembic import op

revision = "054_frappe_ies_bridge"
down_revision = "053_merge_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE tenant_frappe_connections (
            id UUID PRIMARY KEY,
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            hostname VARCHAR(253) NOT NULL,
            encrypted_api_key TEXT NOT NULL,
            encrypted_api_secret TEXT NOT NULL,
            is_enabled BOOLEAN NOT NULL DEFAULT FALSE,
            status VARCHAR(24) NOT NULL DEFAULT 'configured'
                CHECK (status IN ('configured', 'verified', 'disabled', 'error')),
            last_checked_at TIMESTAMPTZ NULL,
            last_error_code VARCHAR(40) NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_tenant_frappe_connections_tenant UNIQUE (tenant_id)
        )
    """)
    op.execute("""
        CREATE TABLE tenant_frappe_student_links (
            id UUID PRIMARY KEY,
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            student_id UUID NOT NULL,
            frappe_student_name VARCHAR(180) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_tenant_frappe_student_link UNIQUE (tenant_id, student_id),
            CONSTRAINT uq_tenant_frappe_remote_student UNIQUE (tenant_id, frappe_student_name),
            CONSTRAINT fk_frappe_link_student_tenant FOREIGN KEY (tenant_id, student_id)
                REFERENCES students(tenant_id, id) ON DELETE CASCADE
        )
    """)
    for table in ("tenant_frappe_connections", "tenant_frappe_student_links"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"""
            CREATE POLICY {table}_tenant_isolation ON {table}
            USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
            WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS tenant_frappe_student_links")
    op.execute("DROP TABLE IF EXISTS tenant_frappe_connections")
