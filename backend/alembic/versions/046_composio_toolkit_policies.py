"""Persist per-tenant Composio toolkit and tool exposure policies.

Revision ID: 046_composio_toolkit_policies
Revises: 045_composio_foundation
"""
from alembic import op

revision = "046_composio_toolkit_policies"
down_revision = "045_composio_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE tenant_composio_toolkit_policies (
            id UUID PRIMARY KEY,
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            toolkit_slug VARCHAR(80) NOT NULL,
            is_enabled BOOLEAN NOT NULL DEFAULT FALSE,
            tool_slugs JSONB NOT NULL DEFAULT '[]'::jsonb,
            updated_by_user_id UUID NULL REFERENCES mira_users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_tenant_composio_toolkit_policy UNIQUE (tenant_id, toolkit_slug),
            CONSTRAINT ck_composio_toolkit_slug CHECK (toolkit_slug ~ '^[a-z0-9][a-z0-9_-]*$'),
            CONSTRAINT ck_composio_tool_slugs_array CHECK (jsonb_typeof(tool_slugs) = 'array'),
            CONSTRAINT ck_composio_enabled_requires_tools CHECK (NOT is_enabled OR jsonb_array_length(tool_slugs) > 0)
        )
    """)
    op.execute("""
        CREATE INDEX ix_tenant_composio_toolkit_policies_enabled
        ON tenant_composio_toolkit_policies (tenant_id, is_enabled)
    """)
    op.execute("ALTER TABLE tenant_composio_toolkit_policies ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE tenant_composio_toolkit_policies FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_composio_toolkit_policies_isolation
        ON tenant_composio_toolkit_policies
        USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS tenant_composio_toolkit_policies")
