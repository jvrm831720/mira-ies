"""Add explicit publication state to prevent cancel/publish races.

Revision ID: 031_rm_sync_publish_boundary
Revises: 030_rm_sync_orchestration
"""
from alembic import op

revision = "031_rm_sync_publish_boundary"
down_revision = "030_rm_sync_orchestration"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE rm_sync_jobs DROP CONSTRAINT ck_rm_sync_jobs_status")
    op.execute("""
        ALTER TABLE rm_sync_jobs ADD CONSTRAINT ck_rm_sync_jobs_status
        CHECK (status IN (
            'queued','running','retry_wait','cancel_requested','publishing',
            'cancelled','succeeded','failed'
        ))
    """)
    op.execute("DROP INDEX IF EXISTS uq_rm_sync_jobs_active_coligada")
    op.execute("""
        CREATE UNIQUE INDEX uq_rm_sync_jobs_active_coligada
        ON rm_sync_jobs(tenant_id, coligada_id)
        WHERE status IN ('queued','running','retry_wait','cancel_requested','publishing')
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_rm_sync_jobs_active_coligada")
    op.execute("""
        UPDATE rm_sync_jobs SET status = 'running'
        WHERE status = 'publishing'
    """)
    op.execute("ALTER TABLE rm_sync_jobs DROP CONSTRAINT ck_rm_sync_jobs_status")
    op.execute("""
        ALTER TABLE rm_sync_jobs ADD CONSTRAINT ck_rm_sync_jobs_status
        CHECK (status IN (
            'queued','running','retry_wait','cancel_requested','cancelled','succeeded','failed'
        ))
    """)
    op.execute("""
        CREATE UNIQUE INDEX uq_rm_sync_jobs_active_coligada
        ON rm_sync_jobs(tenant_id, coligada_id)
        WHERE status IN ('queued','running','retry_wait','cancel_requested')
    """)
