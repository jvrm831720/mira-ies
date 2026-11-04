"""Add action-bound email confirmation challenges for privileged operations.
Revision ID: 038_high_risk_confirmation
Revises: 037_academic_outcomes
"""
from alembic import op
import sqlalchemy as sa
revision = "038_high_risk_confirmation"
down_revision = "037_academic_outcomes"
branch_labels = None
depends_on = None
def upgrade() -> None:
    op.add_column("mira_control_admin_challenges", sa.Column("purpose", sa.String(length=24), nullable=False, server_default="login"))
    op.add_column("mira_control_admin_challenges", sa.Column("action_key", sa.String(length=100), nullable=True))
    op.add_column("mira_control_admin_challenges", sa.Column("payload_hash", sa.String(length=64), nullable=True))
    op.create_index("ix_mira_control_admin_challenges_purpose", "mira_control_admin_challenges", ["purpose", "created_at"])
def downgrade() -> None:
    op.drop_index("ix_mira_control_admin_challenges_purpose", table_name="mira_control_admin_challenges")
    op.drop_column("mira_control_admin_challenges", "payload_hash")
    op.drop_column("mira_control_admin_challenges", "action_key")
    op.drop_column("mira_control_admin_challenges", "purpose")
