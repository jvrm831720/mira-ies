"""Expand personal saved views to academic catalog objects."""
from alembic import op

revision = "068_academic_object_views"
down_revision = "067_retention_proposals_rls"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint("ck_mira_object_views_object", "mira_object_views", type_="check")
    op.create_check_constraint(
        "ck_mira_object_views_object", "mira_object_views",
        "object_key IN ('students','campaigns','academic_classes','academic_programs',"
        "'academic_subjects','academic_teachers','academic_terms')",
    )


def downgrade():
    # Refuse destructive rollback while the added object types have saved views.
    op.drop_constraint("ck_mira_object_views_object", "mira_object_views", type_="check")
    op.create_check_constraint(
        "ck_mira_object_views_object", "mira_object_views",
        "object_key IN ('students','campaigns','academic_classes')",
    )
