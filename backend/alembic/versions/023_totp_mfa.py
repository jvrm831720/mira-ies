"""Add TOTP MFA, recovery codes, login challenges and audit trail.

Revision ID: 023_totp_mfa
Revises: 022_governance_rls_work
"""
from alembic import op
import sqlalchemy as sa

revision = "023_totp_mfa"
down_revision = "022_governance_rls_work"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("mira_users", sa.Column("mfa_totp_secret_encrypted", sa.Text(), nullable=True))
    op.add_column("mira_users", sa.Column("mfa_enabled_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("mira_users", sa.Column("mfa_last_verified_step", sa.Integer(), nullable=True))
    op.add_column("mira_users", sa.Column("mfa_failed_attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("mira_users", sa.Column("mfa_locked_until", sa.DateTime(timezone=True), nullable=True))
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
