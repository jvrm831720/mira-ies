"""Persist confirmed academic outcomes and provenance.

Revision ID: 037_academic_outcomes
Revises: 036_work_activity_prio_campaign
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "037_academic_outcomes"
down_revision = "036_work_activity_prio_campaign"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "training_events",
        sa.Column("outcome_period", sa.String(length=40), nullable=True),
    )
    op.add_column(
        "training_events",
        sa.Column("outcome_source", sa.String(length=40), nullable=True),
    )
    op.create_index(
        "ix_training_events_tenant_outcome_period",
        "training_events",
        ["tenant_id", "outcome_period"],
    )

    op.create_table(
        "academic_outcomes",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("student_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("matricula", sa.String(length=50), nullable=False),
        sa.Column("course", sa.String(length=150), nullable=True),
        sa.Column("academic_period", sa.String(length=40), nullable=True),
        sa.Column("outcome", sa.String(length=40), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("source_record_id", sa.String(length=160), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "source", "source_record_id",
            name="uq_academic_outcomes_tenant_source_record",
        ),
    )
    op.create_index(
        "ix_academic_outcomes_tenant_period",
        "academic_outcomes",
        ["tenant_id", "academic_period"],
    )
    op.create_index(
        "ix_academic_outcomes_tenant_observed",
        "academic_outcomes",
        ["tenant_id", "observed_at"],
    )
    op.create_index(
        "ix_academic_outcomes_tenant_matricula",
        "academic_outcomes",
        ["tenant_id", "matricula"],
    )

    op.execute("ALTER TABLE academic_outcomes ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE academic_outcomes FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY academic_outcomes_tenant_isolation
        ON academic_outcomes
        USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE academic_outcomes NO FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS academic_outcomes_tenant_isolation ON academic_outcomes")
    op.execute("ALTER TABLE academic_outcomes DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_academic_outcomes_tenant_matricula", table_name="academic_outcomes")
    op.drop_index("ix_academic_outcomes_tenant_observed", table_name="academic_outcomes")
    op.drop_index("ix_academic_outcomes_tenant_period", table_name="academic_outcomes")
    op.drop_table("academic_outcomes")
    op.drop_index("ix_training_events_tenant_outcome_period", table_name="training_events")
    op.drop_column("training_events", "outcome_source")
    op.drop_column("training_events", "outcome_period")
