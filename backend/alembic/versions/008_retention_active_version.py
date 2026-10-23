"""Merge existing Alembic heads and enforce one active campaign version per tenant/slug.

Revision ID: 008_retention_active_version
Revises: 007, 007_retention_campaigns
"""
from alembic import op
import sqlalchemy as sa

revision = "008_retention_active_version"
down_revision = ("007", "007_retention_campaigns")
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Normalize existing duplicates before adding the unique partial index.
    # Keep the highest version active for each tenant/campaign slug.
    op.execute("""
        WITH ranked AS (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY tenant_id, slug
                       ORDER BY version DESC, activated_at DESC NULLS LAST, created_at DESC, id
                   ) AS active_rank
            FROM retention_campaigns
            WHERE status = 'active' AND archived IS FALSE
        )
        UPDATE retention_campaigns AS campaigns
        SET status = 'paused', updated_at = now()
        FROM ranked
        WHERE campaigns.id = ranked.id AND ranked.active_rank > 1
    """)
    op.create_index(
        "uq_retention_campaigns_one_active_version",
        "retention_campaigns",
        ["tenant_id", "slug"],
        unique=True,
        postgresql_where=sa.text("status = 'active' AND archived IS FALSE"),
    )


def downgrade() -> None:
    op.drop_index("uq_retention_campaigns_one_active_version", table_name="retention_campaigns")
