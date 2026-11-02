"""Add covering indexes for MFA foreign keys.

Revision ID: 025_mfa_fk_indexes
Revises: 024_mfa_policy_sessions
"""
from alembic import op

revision = "025_mfa_fk_indexes"
down_revision = "024_mfa_policy_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_mira_mfa_audit_user_id",
        "mira_mfa_audit_events",
        ["user_id"],
    )
    op.create_index(
        "ix_mira_mfa_login_challenges_tenant_id",
        "mira_mfa_login_challenges",
        ["tenant_id"],
    )
    op.create_index(
        "ix_mira_tenant_mfa_policies_updated_by_user_id",
        "mira_tenant_mfa_policies",
        ["updated_by_user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_mira_tenant_mfa_policies_updated_by_user_id",
        table_name="mira_tenant_mfa_policies",
    )
    op.drop_index(
        "ix_mira_mfa_login_challenges_tenant_id",
        table_name="mira_mfa_login_challenges",
    )
    op.drop_index(
        "ix_mira_mfa_audit_user_id",
        table_name="mira_mfa_audit_events",
    )
