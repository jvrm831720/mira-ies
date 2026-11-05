"""Merge MIRA Composio dispatch and native academic catalog migration heads.

Revision ID: 058_merge_dispatch_native_academic
Revises: 056_dispatch_composio_ingestion, 057_native_academic_catalog
"""
revision = "058_merge_dispatch_native_academic"
down_revision = ("056_dispatch_composio_ingestion", "057_native_academic_catalog")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
