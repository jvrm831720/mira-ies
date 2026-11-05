"""Tenant-scoped Composio tool approval requests.

Revision ID: 049_composio_tool_approvals
Revises: 048_composio_oauth_states
"""
from alembic import op

revision = "049_composio_tool_approvals"
down_revision = "048_composio_oauth_states"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE tenant_composio_accounts
        ADD CONSTRAINT uq_tenant_composio_account_tenant_id
        UNIQUE (tenant_id, connected_account_id)
    """)
    op.execute("""
        CREATE TABLE tenant_composio_tool_approvals (
            id UUID PRIMARY KEY,
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            connected_account_id VARCHAR(120) NOT NULL,
            requested_by_user_id UUID NOT NULL REFERENCES mira_users(id) ON DELETE RESTRICT,
            reviewed_by_user_id UUID NULL REFERENCES mira_users(id) ON DELETE RESTRICT,
            toolkit_slug VARCHAR(80) NOT NULL,
            tool_slug VARCHAR(120) NOT NULL,
            tool_version VARCHAR(32) NULL,
            arguments_ciphertext TEXT NOT NULL,
            request_fingerprint VARCHAR(64) NOT NULL,
            idempotency_key VARCHAR(120) NOT NULL,
            status VARCHAR(24) NOT NULL DEFAULT 'pending_approval',
            requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            expires_at TIMESTAMPTZ NOT NULL,
            reviewed_at TIMESTAMPTZ NULL,
            executed_at TIMESTAMPTZ NULL,
            execution_id VARCHAR(120) NULL,
            CONSTRAINT fk_composio_approval_account_tenant
                FOREIGN KEY (tenant_id, connected_account_id)
                REFERENCES tenant_composio_accounts (tenant_id, connected_account_id)
                ON DELETE CASCADE,
            CONSTRAINT ck_composio_approval_status
                CHECK (status IN ('pending_approval', 'approved', 'rejected', 'expired', 'cancelled', 'executing', 'succeeded', 'failed', 'unknown')),
            CONSTRAINT ck_composio_approval_four_eyes
                CHECK (reviewed_by_user_id IS NULL OR reviewed_by_user_id <> requested_by_user_id),
            CONSTRAINT uq_composio_approval_idempotency
                UNIQUE (tenant_id, idempotency_key)
        )
    """)
    op.execute("""
        CREATE INDEX ix_composio_approvals_tenant_status_expiry
        ON tenant_composio_tool_approvals (tenant_id, status, expires_at)
    """)
    op.execute("""
        CREATE INDEX ix_composio_approvals_account_status
        ON tenant_composio_tool_approvals (tenant_id, connected_account_id, status)
    """)
    op.execute("ALTER TABLE tenant_composio_tool_approvals ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE tenant_composio_tool_approvals FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_composio_tool_approvals_isolation
        ON tenant_composio_tool_approvals
        USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS tenant_composio_tool_approvals")
    op.execute("ALTER TABLE tenant_composio_accounts DROP CONSTRAINT IF EXISTS uq_tenant_composio_account_tenant_id")
