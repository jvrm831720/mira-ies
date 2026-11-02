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
    # 004_mira_auth may already have created the current model column.
    op.execute(
        "ALTER TABLE mira_mfa_login_challenges "
        "ADD COLUMN IF NOT EXISTS purpose VARCHAR(16) NOT NULL DEFAULT 'verify'"
    )
    from app.db.session import Base
    import app.models  # noqa: F401
    Base.metadata.create_all(bind=op.get_bind(), checkfirst=True)

    # New tenant-owned MFA tables follow the same transaction-scoped tenant
    # isolation used by the existing governance tables. Login challenges are
    # also selectable with a one-time hash supplied by the login flow.
    op.execute("ALTER TABLE mira_tenant_mfa_policies ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE mira_user_sessions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE mira_mfa_login_challenges ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE mira_mfa_audit_events ENABLE ROW LEVEL SECURITY")
    for table in (
        "mira_tenant_mfa_policies",
        "mira_user_sessions",
        "mira_mfa_audit_events",
    ):
        policy_name = f"{table}_tenant_isolation"
        op.execute(f"DROP POLICY IF EXISTS {policy_name} ON {table}")
        op.execute(
            f"""
            CREATE POLICY {policy_name} ON {table}
            USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
            WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
            """
        )
    op.execute("DROP POLICY IF EXISTS mira_mfa_login_challenges_tenant_isolation ON mira_mfa_login_challenges")
    op.execute(
        """
        CREATE POLICY mira_mfa_login_challenges_tenant_isolation
        ON mira_mfa_login_challenges
        USING (
          tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
          OR ticket_hash = NULLIF(current_setting('app.mfa_challenge_hash', true), '')
        )
        WITH CHECK (
          tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        )
        """
    )
    # Existing JWTs have no server-side session id. Invalidate once so every new
    # authenticated session is issued with a revocable database record.
    op.execute(sa.text("UPDATE mira_users SET auth_version = auth_version + 1"))


def downgrade() -> None:
    for table in (
        "mira_mfa_login_challenges",
        "mira_mfa_audit_events",
        "mira_user_sessions",
        "mira_tenant_mfa_policies",
    ):
        if table in {"mira_user_sessions", "mira_tenant_mfa_policies"}:
            op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")
        elif table == "mira_mfa_audit_events":
            op.execute("DROP POLICY IF EXISTS mira_mfa_audit_events_tenant_isolation ON mira_mfa_audit_events")
        else:
            op.execute("DROP POLICY IF EXISTS mira_mfa_login_challenges_tenant_isolation ON mira_mfa_login_challenges")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.drop_table("mira_user_sessions")
    op.drop_table("mira_tenant_mfa_policies")
    op.drop_column("mira_mfa_login_challenges", "purpose")
