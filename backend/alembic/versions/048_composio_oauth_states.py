"""OAuth connect-state table for Composio Connect Link anti-CSRF flow.

Revision ID: 048_composio_oauth_states
Revises: 047_integration_feature_ingestion
"""
from alembic import op

revision = "048_composio_oauth_states"
down_revision = "047_integration_feature_ingestion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE tenant_composio_oauth_states (
            id UUID PRIMARY KEY,
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            toolkit_slug VARCHAR(80) NOT NULL,
            auth_config_id VARCHAR(80) NOT NULL,
            state_token VARCHAR(128) NOT NULL,
            status VARCHAR(24) NOT NULL DEFAULT 'pending',
            created_by_user_id UUID NULL REFERENCES mira_users(id) ON DELETE SET NULL,
            expires_at TIMESTAMPTZ NOT NULL,
            consumed_at TIMESTAMPTZ NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_tenant_composio_oauth_state_token UNIQUE (state_token),
            CONSTRAINT ck_composio_oauth_state_status
                CHECK (status IN ('pending', 'consumed', 'expired', 'failed')),
            CONSTRAINT ck_composio_oauth_toolkit_slug
                CHECK (toolkit_slug ~ '^[a-z0-9][a-z0-9_-]*$')
        )
    """)
    op.execute("""
        CREATE INDEX ix_tenant_composio_oauth_states_tenant_status
        ON tenant_composio_oauth_states (tenant_id, status, expires_at)
    """)
    op.execute("ALTER TABLE tenant_composio_oauth_states ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE tenant_composio_oauth_states FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_composio_oauth_states_isolation
        ON tenant_composio_oauth_states
        USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS tenant_composio_oauth_states")
