"""org members role + invites

Revision ID: 007
Revises: 006
Create Date: 2026-10-21
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "mira_users",
        sa.Column("role", sa.String(length=32), server_default="coordinator", nullable=False),
    )
    op.create_table(
        "mira_org_invites",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("invited_by_user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("mira_users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_mira_org_invites_tenant_status", "mira_org_invites", ["tenant_id", "status"])
    op.create_index("ix_mira_org_invites_email", "mira_org_invites", ["email"])
    op.create_index("ix_mira_org_invites_token_hash", "mira_org_invites", ["token_hash"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_mira_org_invites_token_hash", table_name="mira_org_invites")
    op.drop_index("ix_mira_org_invites_email", table_name="mira_org_invites")
    op.drop_index("ix_mira_org_invites_tenant_status", table_name="mira_org_invites")
    op.drop_table("mira_org_invites")
    op.drop_column("mira_users", "role")
