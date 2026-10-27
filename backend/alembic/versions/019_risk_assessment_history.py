"""Persist tenant-scoped historical risk assessments.

Revision ID: 019_risk_assessment_history
Revises: 018_model_lifecycle
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "019_risk_assessment_history"
down_revision = "018_model_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint("uq_students_tenant_id_id", "students", ["tenant_id", "id"])
    op.create_table(
        "risk_assessments",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True, nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("student_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("batch_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("upload_batches.id", ondelete="SET NULL"), nullable=True),
        sa.Column("scoring_run_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("risk_level", sa.String(length=20), nullable=False),
        sa.Column("model_version", sa.String(length=80), nullable=True),
        sa.Column("model_scope", sa.String(length=20), nullable=False),
        sa.Column("model_score", sa.Float(), nullable=True),
        sa.Column("dynamic_adjustment", sa.Float(), nullable=False, server_default="0"),
        sa.Column("features_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("explanation", postgresql.JSONB(), nullable=True),
        sa.Column("context", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("score >= 0 AND score <= 100", name="ck_risk_assessments_score_range"),
        sa.CheckConstraint("risk_level IN ('baixo', 'medio', 'critico')", name="ck_risk_assessments_level"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "student_id"], ["students.tenant_id", "students.id"],
            name="fk_risk_assessments_tenant_student", ondelete="CASCADE",
        ),
        sa.UniqueConstraint("scoring_run_id", "student_id", name="uq_risk_assessments_run_student"),
    )
    op.create_index("ix_risk_assessments_tenant_evaluated", "risk_assessments", ["tenant_id", "evaluated_at"])
    op.create_index("ix_risk_assessments_tenant_student_evaluated", "risk_assessments", ["tenant_id", "student_id", "evaluated_at"])
    op.create_index("ix_risk_assessments_tenant_level_evaluated", "risk_assessments", ["tenant_id", "risk_level", "evaluated_at"])


def downgrade() -> None:
    op.drop_index("ix_risk_assessments_tenant_level_evaluated", table_name="risk_assessments")
    op.drop_index("ix_risk_assessments_tenant_student_evaluated", table_name="risk_assessments")
    op.drop_index("ix_risk_assessments_tenant_evaluated", table_name="risk_assessments")
    op.drop_table("risk_assessments")
    op.drop_constraint("uq_students_tenant_id_id", "students", type_="unique")
