"""Make Composio tool audit tenant-isolated and append-only.

Revision ID: 050_composio_approval_audit_guards
Revises: 049_composio_tool_approvals
"""
from alembic import op

revision = "050_composio_approval_audit_guards"
down_revision = "049_composio_tool_approvals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE tenant_composio_tool_audit ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE tenant_composio_tool_audit FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_composio_tool_audit_wave3_isolation
        ON tenant_composio_tool_audit
        USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    """)
    op.execute("""
        CREATE OR REPLACE FUNCTION reject_composio_tool_audit_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'tenant_composio_tool_audit is append-only';
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER trg_composio_tool_audit_append_only
        BEFORE UPDATE OR DELETE ON tenant_composio_tool_audit
        FOR EACH ROW EXECUTE FUNCTION reject_composio_tool_audit_mutation()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_composio_tool_audit_append_only ON tenant_composio_tool_audit")
    op.execute("DROP FUNCTION IF EXISTS reject_composio_tool_audit_mutation()")
    op.execute("DROP POLICY IF EXISTS tenant_composio_tool_audit_wave3_isolation ON tenant_composio_tool_audit")
