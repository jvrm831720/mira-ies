"""Wave 1: isolated global student identity, OTP, and revocable sessions.

No tenant debt data is joined or copied. Explicit identity verification is required
before any future cross-institution disclosure.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "073_global_student_identity"
down_revision = "072_federated_search"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=False)


def upgrade():
    op.create_table("mira_global_student_accounts",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("cpf_digest", sa.String(64), nullable=False, unique=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("whatsapp", sa.String(20), nullable=False),
        sa.Column("email_verified_at", sa.DateTime(timezone=True)),
        sa.Column("identity_verified_at", sa.DateTime(timezone=True)),
        sa.Column("identity_verification_method", sa.String(40)),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("identity_verified_at IS NULL OR email_verified_at IS NOT NULL",
                           name="ck_global_identity_requires_email"),
    )
    op.create_index("ix_global_student_email", "mira_global_student_accounts", ["email"])
    op.create_table("mira_global_student_challenges",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("account_id", UUID, sa.ForeignKey("mira_global_student_accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("purpose", sa.String(20), nullable=False),
        sa.Column("code_digest", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("attempts BETWEEN 0 AND 5", name="ck_global_student_challenge_attempts"),
        sa.CheckConstraint("purpose IN ('register','login')", name="ck_global_student_challenge_purpose"),
    )
    op.create_index("ix_global_student_challenge_account", "mira_global_student_challenges",
                    ["account_id", "created_at"])
    op.create_table("mira_global_student_sessions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("account_id", UUID, sa.ForeignKey("mira_global_student_accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_digest", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_global_student_sessions_account", "mira_global_student_sessions",
                    ["account_id", "expires_at"])
    op.create_table("mira_global_student_attestations",
        sa.Column("nonce_digest", sa.String(64), primary_key=True),
        sa.Column("account_id", UUID, sa.ForeignKey("mira_global_student_accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(60), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_global_student_attestation_account", "mira_global_student_attestations", ["account_id"])
    # Backend identity endpoints set this transaction-local scope. Never set it
    # in tenant requests. For production, provision a dedicated auth DB role.
    for table in ("mira_global_student_accounts", "mira_global_student_challenges",
                  "mira_global_student_sessions", "mira_global_student_attestations"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"REVOKE ALL ON TABLE {table} FROM PUBLIC")
        op.execute(f"CREATE POLICY {table}_auth_only ON {table} "
                   "USING (current_setting('app.global_identity_service', true) = 'enabled') "
                   "WITH CHECK (current_setting('app.global_identity_service', true) = 'enabled')")
        # RLS is an extra boundary; provision a dedicated auth DB role in production.

def downgrade():
    # Safest rollback is fail-closed when global identities already exist.
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM mira_global_student_accounts LIMIT 1)
      THEN RAISE EXCEPTION 'Global identities exist; manual reviewed migration required';
      END IF;
    END $$""")
    op.drop_table("mira_global_student_attestations")
    op.drop_table("mira_global_student_sessions")
    op.drop_table("mira_global_student_challenges")
    op.drop_table("mira_global_student_accounts")
