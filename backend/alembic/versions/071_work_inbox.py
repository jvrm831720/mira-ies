"""Wave 5: monotonic work revision and event idempotency keys.

Revision ID: 071_work_inbox
Revises: 070_object_view_collaboration
No task, intervention, dispatch or financial row is reclassified.
"""
from alembic import op
import sqlalchemy as sa

revision = "071_work_inbox"
down_revision = "070_object_view_collaboration"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "work_activities",
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_check_constraint(
        "ck_work_activities_revision", "work_activities", "revision >= 1"
    )
    op.add_column(
        "work_activity_events", sa.Column("operation_key", sa.String(80), nullable=True)
    )
    op.create_index(
        "uq_work_activity_events_operation_key",
        "work_activity_events",
        ["tenant_id", "activity_id", "operation_key"],
        unique=True,
        postgresql_where=sa.text("operation_key IS NOT NULL"),
    )
    op.create_index(
        "ix_work_activities_inbox_paging",
        "work_activities", ["tenant_id", "status", "assignee_user_id", "due_at", "id"],
    )


def downgrade():
    # Preserve idempotency evidence: never silently permit replay after rollback.
    op.execute("""
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM work_activity_events
                     WHERE operation_key IS NOT NULL)
          THEN RAISE EXCEPTION 'Work inbox operation keys exist; export before rollback';
          END IF;
        END $$
    """)
    op.drop_index("ix_work_activities_inbox_paging", table_name="work_activities")
    op.drop_index("uq_work_activity_events_operation_key", table_name="work_activity_events")
    op.drop_column("work_activity_events", "operation_key")
    op.drop_constraint("ck_work_activities_revision", "work_activities", type_="check")
    op.drop_column("work_activities", "revision")
