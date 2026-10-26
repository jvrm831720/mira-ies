"""Add historical data-use modality and authorization evidence per tenant.

Revision ID: 016_tenant_data_use_policy
Revises: 015_student_campus_status
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "016_tenant_data_use_policy"
down_revision = "015_student_campus_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant_data_use_policies",
        sa.Column(
            "id", postgresql.UUID(as_uuid=False), primary_key=True, nullable=False
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("contract_reference", sa.String(length=160), nullable=False),
        sa.Column("contract_version", sa.String(length=80), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "approved_by_admin_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("mira_control_admins.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("evidence_reference", sa.String(length=500), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "mode IN ('shared_training', 'institution_only')",
            name="ck_tenant_data_use_policy_mode",
        ),
        sa.CheckConstraint(
            "expires_at IS NULL OR expires_at > effective_at",
            name="ck_tenant_data_use_policy_expiry",
        ),
    )
    op.create_index(
        "ix_tenant_data_use_policy_tenant_effective",
        "tenant_data_use_policies",
        ["tenant_id", "effective_at"],
    )
    op.create_index(
        "ix_tenant_data_use_policy_tenant_revoked",
        "tenant_data_use_policies",
        ["tenant_id", "revoked_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_tenant_data_use_policy_tenant_revoked",
        table_name="tenant_data_use_policies",
    )
    op.drop_index(
        "ix_tenant_data_use_policy_tenant_effective",
        table_name="tenant_data_use_policies",
    )
    op.drop_table("tenant_data_use_policies")
