"""Add safe delivery correlation, idempotency and webhook status fields.

Revision ID: 006_safe_agent_delivery
Revises: 005_student_opt_out
"""
from typing import Sequence, Union

from alembic import op

revision: str = "006_safe_agent_delivery"
down_revision: Union[str, None] = "005_student_opt_out"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE intervention_logs ADD COLUMN IF NOT EXISTS correlation_id VARCHAR(160)")
    op.execute("ALTER TABLE intervention_logs ADD COLUMN IF NOT EXISTS idempotency_key VARCHAR(255)")
    op.execute("ALTER TABLE intervention_logs ADD COLUMN IF NOT EXISTS job_id VARCHAR(80)")
    op.execute("ALTER TABLE intervention_logs ADD COLUMN IF NOT EXISTS campaign_id VARCHAR(120)")
    op.execute("ALTER TABLE intervention_logs ADD COLUMN IF NOT EXISTS delivery_status VARCHAR(30)")
    op.execute("ALTER TABLE intervention_logs ADD COLUMN IF NOT EXISTS delivery_event_id VARCHAR(160)")
    op.execute("ALTER TABLE intervention_logs ADD COLUMN IF NOT EXISTS delivery_updated_at TIMESTAMPTZ")
    op.execute("""
    DO $$ BEGIN
      IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_intervention_logs_tenant_idempotency_key'
      ) THEN
        ALTER TABLE intervention_logs
          ADD CONSTRAINT uq_intervention_logs_tenant_idempotency_key
          UNIQUE (tenant_id, idempotency_key);
      END IF;
    END $$;
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_intervention_logs_correlation_id ON intervention_logs (correlation_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_intervention_logs_job_id ON intervention_logs (job_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_intervention_logs_campaign_id ON intervention_logs (campaign_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_intervention_logs_tenant_external_id ON intervention_logs (tenant_id, external_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_intervention_logs_tenant_external_id")
    op.execute("DROP INDEX IF EXISTS ix_intervention_logs_campaign_id")
    op.execute("DROP INDEX IF EXISTS ix_intervention_logs_job_id")
    op.execute("DROP INDEX IF EXISTS ix_intervention_logs_correlation_id")
    op.execute("ALTER TABLE intervention_logs DROP CONSTRAINT IF EXISTS uq_intervention_logs_tenant_idempotency_key")
    op.execute("ALTER TABLE intervention_logs DROP COLUMN IF EXISTS delivery_updated_at")
    op.execute("ALTER TABLE intervention_logs DROP COLUMN IF EXISTS delivery_event_id")
    op.execute("ALTER TABLE intervention_logs DROP COLUMN IF EXISTS delivery_status")
    op.execute("ALTER TABLE intervention_logs DROP COLUMN IF EXISTS campaign_id")
    op.execute("ALTER TABLE intervention_logs DROP COLUMN IF EXISTS job_id")
    op.execute("ALTER TABLE intervention_logs DROP COLUMN IF EXISTS idempotency_key")
    op.execute("ALTER TABLE intervention_logs DROP COLUMN IF EXISTS correlation_id")
