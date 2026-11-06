"""Persist bounded workspace logos during verified onboarding.

Revision ID: 069_onboarding_logo
Revises: 068_academic_object_views
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "069_onboarding_logo"
down_revision = "068_academic_object_views"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "mira_tenant_logo_assets",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("content_type", sa.String(32), nullable=False),
        sa.Column("image_bytes", sa.LargeBinary(), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("octet_length(image_bytes) > 0 AND octet_length(image_bytes) <= 2000000", name="ck_mira_tenant_logo_assets_size"),
        sa.CheckConstraint("content_type IN ('image/png', 'image/jpeg', 'image/webp')", name="ck_mira_tenant_logo_assets_type"),
        sa.CheckConstraint("source IN ('uploaded', 'site_favicon')", name="ck_mira_tenant_logo_assets_source"),
    )
    op.execute("ALTER TABLE mira_tenant_logo_assets ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE mira_tenant_logo_assets FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY mira_tenant_logo_assets_isolation
        ON mira_tenant_logo_assets FOR ALL
        USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    """)
    op.execute("REVOKE ALL ON TABLE mira_tenant_logo_assets FROM PUBLIC")
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
                REVOKE ALL ON TABLE mira_tenant_logo_assets FROM anon;
            END IF;
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
                REVOKE ALL ON TABLE mira_tenant_logo_assets FROM authenticated;
            END IF;
        END;
        $$
    """)


def downgrade():
    op.drop_table("mira_tenant_logo_assets")
