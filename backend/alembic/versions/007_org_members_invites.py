"""org members role + invites

Revision ID: 007
Revises: 006_safe_agent_delivery
Create Date: 2026-10-21
"""
from alembic import op

revision = "007"
down_revision = "006_safe_agent_delivery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE mira_users ADD COLUMN IF NOT EXISTS role VARCHAR(32) NOT NULL DEFAULT 'coordinator'")
    op.execute("ALTER TABLE mira_users ALTER COLUMN role SET DEFAULT 'coordinator'")
    op.execute("""
    CREATE TABLE IF NOT EXISTS mira_org_invites (
        id UUID PRIMARY KEY,
        tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        email VARCHAR(255) NOT NULL,
        role VARCHAR(32) NOT NULL,
        token_hash VARCHAR(64) NOT NULL,
        status VARCHAR(20) NOT NULL,
        invited_by_user_id UUID REFERENCES mira_users(id) ON DELETE SET NULL,
        expires_at TIMESTAMPTZ NOT NULL,
        accepted_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL
    )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_mira_org_invites_tenant_status ON mira_org_invites (tenant_id, status)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_mira_org_invites_email ON mira_org_invites (email)")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_mira_org_invites_token_hash ON mira_org_invites (token_hash)")


def downgrade() -> None:
    # As revisões anteriores materializam o metadata ORM atual, não é seguro
    # remover aqui colunas/tabelas que já pertenciam ao schema-base.
    pass
