"""Add independent authorization evidence for institution-only training.

Revision ID: 017_inst_training_auth
Revises: 016_tenant_data_use_policy
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "017_inst_training_auth"
down_revision = "016_tenant_data_use_policy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "institutional_training_authorizations",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True, nullable=False),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
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
        sa.Column("dataset_eligibility_reference", sa.String(length=500), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "expires_at IS NULL OR expires_at > effective_at",
            name="ck_institutional_training_auth_expiry",
        ),
    )
    op.create_index(
        "ix_institutional_training_auth_tenant_effective",
        "institutional_training_authorizations",
        ["tenant_id", "effective_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_institutional_training_auth_tenant_effective",
        table_name="institutional_training_authorizations",
    )
    op.drop_table("institutional_training_authorizations")
