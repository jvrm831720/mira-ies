"""Allow append-only revocation events without reusing eligible contributions.

Revision ID: 055_eligible_contrib_revocation
Revises: 054_smart_import_custom_fields
"""
from alembic import op

revision = "055_eligible_contrib_revocation"
down_revision = "054_smart_import_custom_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Preserve the old eligible-row idempotency guarantee while making room
    # for a revoked event with the same hash in the immutable audit trail.
    op.drop_constraint(
        "uq_eligible_contributions_idempotent",
        "eligible_contributions",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_eligible_contributions_idempotent",
        "eligible_contributions",
        ["tenant_id", "contribution_key", "sanitized_content_hash", "eligibility_status"],
    )


def downgrade() -> None:
    # A downgrade is safe only if the records can satisfy the older rule;
    # operator must resolve conflicting history without silently deleting it.
    op.drop_constraint(
        "uq_eligible_contributions_idempotent",
        "eligible_contributions",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_eligible_contributions_idempotent",
        "eligible_contributions",
        ["tenant_id", "contribution_key", "sanitized_content_hash"],
    )
