"""Operational lifecycle foundation for retention campaign proposals.

Revision ID: 036_retention_campaign_lifecycle
Revises: 035_retention_campaign_workflow
"""
from alembic import op
import sqlalchemy as sa

revision = "036_retention_campaign_lifecycle"
down_revision = "035_retention_campaign_workflow"
branch_labels = None
depends_on = None

_OPERATIONAL_STATUSES = (
    "draft", "in_review", "changes_requested", "approved", "scheduled",
    "running", "paused", "completed", "cancelled", "failed",
)


def upgrade() -> None:
    op.drop_constraint(
        "ck_retention_campaign_proposals_status",
        "retention_campaign_proposals",
        type_="check",
    )
    op.create_check_constraint(
        "ck_retention_campaign_proposals_status",
        "retention_campaign_proposals",
        "status IN (" + ", ".join(repr(value) for value in _OPERATIONAL_STATUSES) + ")",
    )
    op.add_column(
        "retention_campaign_proposals",
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "retention_campaign_proposals",
        sa.Column("schedule_timezone", sa.String(64), nullable=True),
    )
    op.add_column(
        "retention_campaign_proposals",
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "retention_campaign_proposals",
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "retention_campaign_proposals",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "retention_campaign_proposals",
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "retention_campaign_proposals",
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_retention_campaign_proposals_schedule_pair",
        "retention_campaign_proposals",
        "((scheduled_for IS NULL AND schedule_timezone IS NULL) OR "
        "(scheduled_for IS NOT NULL AND schedule_timezone IS NOT NULL "
        "AND length(trim(schedule_timezone)) > 0))",
    )
    op.create_index(
        "ix_retention_campaign_proposals_tenant_scheduled",
        "retention_campaign_proposals",
        ["tenant_id", "scheduled_for"],
        postgresql_where=sa.text("status = 'scheduled'"),
    )


def downgrade() -> None:
    # Preserve proposals if an operator rolls back while operational states exist.
    op.execute(
        "UPDATE retention_campaign_proposals "
        "SET status = 'approved' "
        "WHERE status IN ('scheduled', 'running', 'paused', 'completed', 'cancelled', 'failed')"
    )
    op.drop_index(
        "ix_retention_campaign_proposals_tenant_scheduled",
        table_name="retention_campaign_proposals",
    )
    op.drop_constraint(
        "ck_retention_campaign_proposals_schedule_pair",
        "retention_campaign_proposals",
        type_="check",
    )
    for column in (
        "failed_at", "cancelled_at", "completed_at", "paused_at",
        "started_at", "schedule_timezone", "scheduled_for",
    ):
        op.drop_column("retention_campaign_proposals", column)
    op.drop_constraint(
        "ck_retention_campaign_proposals_status",
        "retention_campaign_proposals",
        type_="check",
    )
    op.create_check_constraint(
        "ck_retention_campaign_proposals_status",
        "retention_campaign_proposals",
        "status IN ('draft', 'in_review', 'changes_requested', 'approved')",
    )
