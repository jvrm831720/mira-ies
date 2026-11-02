"""Add TOTP MFA, recovery codes, login challenges and audit trail.

Revision ID: 023_totp_mfa
Revises: 022_governance_rls_work
"""
from alembic import op

revision = "023_totp_mfa"
down_revision = "022_governance_rls_work"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 004_mira_auth usa Base.metadata.create_all. Em bases novas, esse
    # create_all pode já ter criado colunas dos modelos atuais. IF NOT EXISTS
    # mantém a migration segura tanto em bases novas quanto em instalações antigas.
    op.execute("ALTER TABLE mira_users ADD COLUMN IF NOT EXISTS mfa_totp_secret_encrypted TEXT")
    op.execute("ALTER TABLE mira_users ADD COLUMN IF NOT EXISTS mfa_enabled_at TIMESTAMPTZ")
    op.execute("ALTER TABLE mira_users ADD COLUMN IF NOT EXISTS mfa_last_verified_step INTEGER")
    op.execute("ALTER TABLE mira_users ADD COLUMN IF NOT EXISTS mfa_failed_attempts INTEGER NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE mira_users ADD COLUMN IF NOT EXISTS mfa_locked_until TIMESTAMPTZ")
    from app.db.session import Base
    import app.models  # noqa: F401
    Base.metadata.create_all(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    op.drop_table("mira_mfa_audit_events")
    op.drop_table("mira_mfa_recovery_codes")
    op.drop_table("mira_mfa_login_challenges")
    op.drop_column("mira_users", "mfa_locked_until")
    op.drop_column("mira_users", "mfa_failed_attempts")
    op.drop_column("mira_users", "mfa_last_verified_step")
    op.drop_column("mira_users", "mfa_enabled_at")
    op.drop_column("mira_users", "mfa_totp_secret_encrypted")
