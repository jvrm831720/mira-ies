"""Read-only Composio financial sync audit.

Revision ID: 060_student_finance_composio
Revises: 059_student_services
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "060_student_finance_composio"
down_revision = "059_student_services"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "mira_student_financial_sync_runs",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("connected_account_id", sa.String(120), nullable=False),
        sa.Column("toolkit", sa.String(80), nullable=False),
        sa.Column("tool_slug", sa.String(120), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(120), nullable=False),
        sa.Column("record_count", sa.Integer(), nullable=False),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "id", name="uq_student_finance_sync_tenant_id"),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_student_finance_sync_key"),
        sa.CheckConstraint("record_count >= 0 AND record_count <= 100", name="ck_student_finance_sync_records"),
    )
    op.create_index("ix_student_finance_sync_tenant_time", "mira_student_financial_sync_runs", ["tenant_id", "synced_at"])
    op.execute("ALTER TABLE mira_student_financial_sync_runs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE mira_student_financial_sync_runs FORCE ROW LEVEL SECURITY")
    op.execute("""CREATE POLICY mira_student_financial_sync_runs_tenant_access
        ON mira_student_financial_sync_runs
        USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)""")
    op.get_bind().exec_driver_sql("""
        CREATE FUNCTION mira_financial_sync_immutable() RETURNS trigger AS $finance4$
        BEGIN
            RAISE EXCEPTION 'financial sync audit is append-only';
        END;
        $finance4$ LANGUAGE plpgsql
    """)
    op.execute("""CREATE TRIGGER mira_financial_sync_immutable
        BEFORE UPDATE OR DELETE ON mira_student_financial_sync_runs
        FOR EACH ROW EXECUTE FUNCTION mira_financial_sync_immutable()""")


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS mira_financial_sync_immutable ON mira_student_financial_sync_runs")
    op.execute("DROP FUNCTION IF EXISTS mira_financial_sync_immutable()")
    op.drop_table("mira_student_financial_sync_runs")
