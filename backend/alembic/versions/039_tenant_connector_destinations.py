"""Persist exact outbound destinations per tenant and connector.

Revision ID: 039_tenant_conn_dest
Revises: 038_high_risk_confirmation
"""
from alembic import op

revision = "039_tenant_conn_dest"
down_revision = "038_high_risk_confirmation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE tenant_connector_destinations (
            id UUID PRIMARY KEY,
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            connector_key VARCHAR(40) NOT NULL,
            hostname VARCHAR(253) NOT NULL,
            scheme VARCHAR(5) NOT NULL DEFAULT 'https' CHECK (scheme = 'https'),
            port INTEGER NOT NULL DEFAULT 443 CHECK (port = 443),
            is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
            approval_reason VARCHAR(500) NOT NULL,
            approved_by_user_id UUID NULL REFERENCES mira_users(id) ON DELETE SET NULL,
            approved_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_tenant_connector_destination UNIQUE
                (tenant_id, connector_key, hostname, port)
        )
    """)
    op.execute("CREATE INDEX ix_tenant_connector_destinations_tenant_connector ON tenant_connector_destinations (tenant_id, connector_key, is_enabled)")
    op.execute("""
        CREATE TABLE tenant_connector_destination_audit (
            id UUID PRIMARY KEY,
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            destination_id UUID NULL,
            connector_key VARCHAR(40) NOT NULL,
            hostname VARCHAR(253) NOT NULL,
            action VARCHAR(16) NOT NULL CHECK (action IN ('approved', 'revoked')),
            reason VARCHAR(500) NOT NULL,
            actor_user_id UUID NULL REFERENCES mira_users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX ix_tenant_connector_destination_audit_tenant_created ON tenant_connector_destination_audit (tenant_id, created_at DESC)")
    op.execute("""
        CREATE FUNCTION reject_connector_destination_audit_mutation()
        RETURNS trigger LANGUAGE plpgsql
        AS 'BEGIN RAISE EXCEPTION ''connector destination audit is append-only''; END;'
    """)
    op.execute("""
        CREATE TRIGGER tenant_connector_destination_audit_append_only
        BEFORE UPDATE OR DELETE ON tenant_connector_destination_audit
        FOR EACH ROW EXECUTE FUNCTION reject_connector_destination_audit_mutation()
    """)
    for table in ("tenant_connector_destinations", "tenant_connector_destination_audit"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"""
            CREATE POLICY {table}_isolation ON {table}
            USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
            WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS tenant_connector_destination_audit")
    op.execute("DROP FUNCTION IF EXISTS reject_connector_destination_audit_mutation()")
    op.execute("DROP TABLE IF EXISTS tenant_connector_destinations")
