"""Add institutional MFA policies, revocable sessions and enrollment challenge type.

Revision ID: 024_mfa_policy_sessions
Revises: 023_totp_mfa
"""
from alembic import op
import sqlalchemy as sa

revision = "024_mfa_policy_sessions"
down_revision = "023_totp_mfa"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "mira_mfa_login_challenges",
        sa.Column("purpose", sa.String(length=16), nullable=False, server_default="verify"),
    )
    from app.db.session import Base
    import app.models  # noqa: F401
    Base.metadata.create_all(bind=op.get_bind(), checkfirst=True)
    # Existing JWTs have no server-side session id. Invalidate once so every new
    # authenticated session is issued with a revocable database record.
    op.execute(sa.text("UPDATE mira_users SET auth_version = auth_version + 1"))


def downgrade() -> None:
    op.drop_table("mira_user_sessions")
    op.drop_table("mira_tenant_mfa_policies")
    op.drop_column("mira_mfa_login_challenges", "purpose")
