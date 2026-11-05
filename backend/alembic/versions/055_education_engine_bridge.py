"""Self-hosted Frappe Education engine tenancy and verified student links.

Revision ID: 055_education_engine_bridge
Revises: 054_smart_import_custom_fields
"""
from alembic import op

revision = "055_education_engine_bridge"
down_revision = "054_smart_import_custom_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE tenant_education_engine_connections (
            id UUID PRIMARY KEY,
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            site_name VARCHAR(200) NOT NULL,
            encrypted_api_key TEXT NOT NULL,
            encrypted_api_secret TEXT NOT NULL,
            is_enabled BOOLEAN NOT NULL DEFAULT FALSE,
            status VARCHAR(24) NOT NULL DEFAULT 'configured'
                CHECK (status IN ('configured','verified','disabled','error')),
            verified_at TIMESTAMPTZ,
            last_error_code VARCHAR(40),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_education_engine_tenant UNIQUE (tenant_id),
            CONSTRAINT uq_education_engine_site UNIQUE (site_name)
        )
    """)
    op.execute("""
        CREATE TABLE tenant_education_engine_students (
            id UUID PRIMARY KEY,
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            student_id UUID NOT NULL,
            frappe_student_id VARCHAR(180) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT fk_education_engine_tenant_student
                FOREIGN KEY (tenant_id,student_id)
                REFERENCES students(tenant_id,id) ON DELETE CASCADE,
            CONSTRAINT uq_education_engine_local_student UNIQUE (tenant_id,student_id),
            CONSTRAINT uq_education_engine_remote_student UNIQUE (tenant_id,frappe_student_id)
        )
    """)
    op.execute("""
        CREATE TABLE tenant_education_engine_audit (
            id UUID PRIMARY KEY,
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            event_type VARCHAR(64) NOT NULL,
            actor_user_id UUID,
            student_id UUID,
            occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX ix_education_engine_audit_tenant_time
        ON tenant_education_engine_audit(tenant_id, occurred_at)
    """)
    for name in (
        "tenant_education_engine_connections",
        "tenant_education_engine_students",
        "tenant_education_engine_audit",
    ):
        op.execute(f"ALTER TABLE {name} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {name} FORCE ROW LEVEL SECURITY")
    for name in ("tenant_education_engine_connections", "tenant_education_engine_students"):
        op.execute(f"""
            CREATE POLICY {name}_tenant ON {name}
            USING (tenant_id = NULLIF(current_setting('app.tenant_id',true),'')::uuid)
            WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id',true),'')::uuid)
        """)
    op.execute("""
        CREATE POLICY tenant_education_engine_audit_read ON tenant_education_engine_audit
        FOR SELECT USING (tenant_id = NULLIF(current_setting('app.tenant_id',true),'')::uuid)
    """)
    op.execute("""
        CREATE POLICY tenant_education_engine_audit_insert ON tenant_education_engine_audit
        FOR INSERT WITH CHECK (
            tenant_id = NULLIF(current_setting('app.tenant_id',true),'')::uuid
        )
    """)
    # No UPDATE/DELETE audit policy: append-only for tenant role, including owner via FORCE RLS.


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS tenant_education_engine_audit")
    op.execute("DROP TABLE IF EXISTS tenant_education_engine_students")
    op.execute("DROP TABLE IF EXISTS tenant_education_engine_connections")
