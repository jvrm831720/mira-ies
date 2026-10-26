"""Add auditable model lifecycle states and explicit approval metadata.

Revision ID: 018_model_lifecycle
Revises: 017_inst_training_auth
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "018_model_lifecycle"
down_revision = "017_inst_training_auth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("model_artifacts", sa.Column("run_id", postgresql.UUID(as_uuid=False), nullable=True))
    op.create_unique_constraint("uq_model_artifacts_run_id", "model_artifacts", ["run_id"])
    op.add_column(
        "model_artifacts",
        sa.Column("lifecycle_status", sa.String(length=20), nullable=False, server_default="candidate"),
    )
    op.add_column("model_artifacts", sa.Column("evaluation_report", postgresql.JSONB(), nullable=True))
    op.add_column(
        "model_artifacts",
        sa.Column("approved_by_user_id", postgresql.UUID(as_uuid=False), nullable=True),
    )
    op.create_foreign_key(
        "fk_model_artifacts_approved_by_user", "model_artifacts", "users",
        ["approved_by_user_id"], ["id"], ondelete="SET NULL",
    )
    op.add_column("model_artifacts", sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("model_artifacts", sa.Column("activation_reason", sa.String(length=500), nullable=True))
    op.add_column("model_artifacts", sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("model_artifacts", sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "model_artifacts",
        sa.Column("rollback_of_artifact_id", postgresql.UUID(as_uuid=False), nullable=True),
    )
    op.create_foreign_key(
        "fk_model_artifacts_rollback_of", "model_artifacts", "model_artifacts",
        ["rollback_of_artifact_id"], ["id"], ondelete="SET NULL",
    )
    op.execute("UPDATE model_artifacts SET lifecycle_status = 'active' WHERE is_active = true")
    op.create_check_constraint(
        "ck_model_artifacts_lifecycle_status",
        "model_artifacts",
        "lifecycle_status IN ('candidate', 'approved', 'active', 'retired', 'rejected')",
    )
    op.create_index(
        "ix_model_artifacts_lifecycle",
        "model_artifacts",
        ["tenant_id", "scope", "lifecycle_status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_model_artifacts_lifecycle", table_name="model_artifacts")
    op.drop_constraint("ck_model_artifacts_lifecycle_status", "model_artifacts", type_="check")
    op.drop_constraint("fk_model_artifacts_rollback_of", "model_artifacts", type_="foreignkey")
    op.drop_column("model_artifacts", "rollback_of_artifact_id")
    op.drop_column("model_artifacts", "retired_at")
    op.drop_column("model_artifacts", "activated_at")
    op.drop_column("model_artifacts", "activation_reason")
    op.drop_column("model_artifacts", "approved_at")
    op.drop_constraint("fk_model_artifacts_approved_by_user", "model_artifacts", type_="foreignkey")
    op.drop_column("model_artifacts", "approved_by_user_id")
    op.drop_column("model_artifacts", "evaluation_report")
    op.drop_column("model_artifacts", "lifecycle_status")
    op.drop_constraint("uq_model_artifacts_run_id", "model_artifacts", type_="unique")
    op.drop_column("model_artifacts", "run_id")
