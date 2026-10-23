"""Internal identities, email MFA challenges, and audit events for Control Center.

Revision ID: 012_control_center_admin
Revises: 011_retention_observability
"""
from alembic import op

revision = "012_control_center_admin"
down_revision = "011_retention_observability"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS mira_control_admins (
            id UUID PRIMARY KEY,
            email VARCHAR(255) NOT NULL,
            display_name VARCHAR(120) NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            role VARCHAR(32) NOT NULL DEFAULT 'support',
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            failed_login_attempts INTEGER NOT NULL DEFAULT 0,
            locked_until TIMESTAMPTZ,
            auth_version INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_mira_control_admins_email UNIQUE (email)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_mira_control_admins_active
        ON mira_control_admins (is_active)
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS mira_control_admin_challenges (
            id UUID PRIMARY KEY,
            admin_id UUID NOT NULL REFERENCES mira_control_admins(id) ON DELETE CASCADE,
            email_hash VARCHAR(64) NOT NULL,
            code_hash VARCHAR(64) NOT NULL,
            expires_at TIMESTAMPTZ NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            consumed_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_mira_control_admin_challenge_lookup
        ON mira_control_admin_challenges (email_hash, created_at)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_mira_control_admin_challenge_expiry
        ON mira_control_admin_challenges (expires_at)
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS mira_control_admin_audit (
            id UUID PRIMARY KEY,
            actor_admin_id UUID REFERENCES mira_control_admins(id) ON DELETE SET NULL,
            action VARCHAR(100) NOT NULL,
            result VARCHAR(32) NOT NULL,
            target_type VARCHAR(80),
            target_id VARCHAR(100),
            reason VARCHAR(500),
            request_id VARCHAR(100),
            metadata_redacted JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_mira_control_admin_audit_created
        ON mira_control_admin_audit (created_at)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_mira_control_admin_audit_actor
        ON mira_control_admin_audit (actor_admin_id, created_at)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_mira_control_admin_audit_actor")
    op.execute("DROP INDEX IF EXISTS ix_mira_control_admin_audit_created")
    op.execute("DROP TABLE IF EXISTS mira_control_admin_audit")
    op.execute("DROP INDEX IF EXISTS ix_mira_control_admin_challenge_expiry")
    op.execute("DROP INDEX IF EXISTS ix_mira_control_admin_challenge_lookup")
    op.execute("DROP TABLE IF EXISTS mira_control_admin_challenges")
    op.execute("DROP INDEX IF EXISTS ix_mira_control_admins_active")
    op.execute("DROP TABLE IF EXISTS mira_control_admins")
