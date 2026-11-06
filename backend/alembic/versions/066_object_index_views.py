"""Wave 0.1: tenant and identity isolated Object Index saved views.

Revision ID: 066_object_index_views
Revises: 065_academic_operations
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "066_object_index_views"
down_revision = "065_academic_operations"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "mira_object_views",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("owner_user_id", UUID(as_uuid=False), sa.ForeignKey("mira_users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("object_key", sa.String(36), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("config_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("config", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "id", name="uq_mira_object_views_tenant_id"),
        sa.UniqueConstraint("tenant_id", "owner_user_id", "object_key", "name", name="uq_mira_object_views_owner_name"),
        sa.CheckConstraint("config_version = 1", name="ck_mira_object_views_version"),
        sa.CheckConstraint("object_key IN ('students','campaigns','academic_classes')", name="ck_mira_object_views_object"),
    )
    op.create_index("ix_mira_object_views_owner", "mira_object_views", ["tenant_id", "owner_user_id", "object_key"])
    op.execute("ALTER TABLE mira_object_views ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE mira_object_views FORCE ROW LEVEL SECURITY")
    op.execute("""CREATE POLICY mira_object_views_owner_policy ON mira_object_views
        USING (
          tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
          AND owner_user_id = NULLIF(current_setting('app.user_id', true), '')::uuid
        )
        WITH CHECK (
          tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
          AND owner_user_id = NULLIF(current_setting('app.user_id', true), '')::uuid
        )""")

def downgrade():
    op.drop_table("mira_object_views")
