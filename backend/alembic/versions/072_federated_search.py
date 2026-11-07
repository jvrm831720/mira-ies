"""Wave 6 — PostgreSQL trigram indexes for tenant-constrained federated search.

Revision ID: 072_federated_search
Revises: 071_work_inbox

Only additive extension/index DDL; no records are copied or reclassified.
"""
from alembic import op

revision = "072_federated_search"
down_revision = "071_work_inbox"
branch_labels = None
depends_on = None

_INDEXES = {
    "ix_search_students_name_trgm": "students USING gin (lower(nome) gin_trgm_ops)",
    "ix_search_students_enrollment_trgm": "students USING gin (lower(matricula) gin_trgm_ops)",
    "ix_search_finance_external_ref_trgm": "dispatch_obligations USING gin (lower(external_ref) gin_trgm_ops)",
    "ix_search_finance_subject_ref_trgm": "dispatch_obligations USING gin (lower(subject_ref) gin_trgm_ops)",
    "ix_search_work_title_trgm": "work_activities USING gin (lower(title) gin_trgm_ops)",
    "ix_search_view_name_trgm": "mira_object_views USING gin (lower(name) gin_trgm_ops)",
    "ix_search_proposal_title_trgm": "retention_campaign_proposals USING gin (lower(title) gin_trgm_ops)",
}


def upgrade() -> None:
    # pg_trgm is a trusted PostgreSQL extension on supported versions and is
    # installed by the normal migration runner, never by the HTTP request.
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    for name, definition in _INDEXES.items():
        op.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {definition}")


def downgrade() -> None:
    for name in reversed(_INDEXES):
        op.execute(f"DROP INDEX IF EXISTS {name}")
    # Keep shared pg_trgm extension: other app features may depend on it.
