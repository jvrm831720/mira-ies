"""Self-serve onboarding sessions and institution profile.

Revision ID: 052_self_serve_onboarding
Revises: 051_organization_membership
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "052_self_serve_onboarding"
down_revision: Union[str, None] = "051_organization_membership"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("mira_organizations", sa.Column("website_url", sa.String(500), nullable=True))
    op.add_column("mira_organizations", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("mira_organizations", sa.Column("profile_data", postgresql.JSONB(), nullable=True))

    op.create_table(
        "mira_onboarding_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("draft_data", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("current_step", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("mira_users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("mira_organizations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("token_hash", name="uq_mira_onboarding_sessions_token_hash"),
    )
    op.create_index("ix_mira_onboarding_sessions_email", "mira_onboarding_sessions", ["email"])
    op.create_index("ix_mira_onboarding_sessions_expires", "mira_onboarding_sessions", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_mira_onboarding_sessions_expires", table_name="mira_onboarding_sessions")
    op.drop_index("ix_mira_onboarding_sessions_email", table_name="mira_onboarding_sessions")
    op.drop_table("mira_onboarding_sessions")
    op.drop_column("mira_organizations", "profile_data")
    op.drop_column("mira_organizations", "description")
    op.drop_column("mira_organizations", "website_url")
