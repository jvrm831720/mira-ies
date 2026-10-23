"""Provider attempt telemetry for retention analytics.

Revision ID: 011_retention_observability
Revises: 010_smart_crm_engine
"""
from alembic import op

revision = "011_retention_observability"
down_revision = "010_smart_crm_engine"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS provider_call_metrics (
            id UUID PRIMARY KEY,
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            intervention_log_id UUID NOT NULL REFERENCES intervention_logs(id) ON DELETE CASCADE,
            channel VARCHAR(20) NOT NULL,
            provider VARCHAR(40) NOT NULL,
            latency_ms DOUBLE PRECISION NOT NULL,
            succeeded BOOLEAN NOT NULL DEFAULT FALSE,
            provider_outcome VARCHAR(40) NOT NULL,
            occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_provider_call_metrics_tenant_time
        ON provider_call_metrics (tenant_id, occurred_at)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_provider_call_metrics_tenant_channel_provider_time
        ON provider_call_metrics (tenant_id, channel, provider, occurred_at)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_provider_call_metrics_tenant_channel_provider_time")
    op.execute("DROP INDEX IF EXISTS ix_provider_call_metrics_tenant_time")
    op.execute("DROP TABLE IF EXISTS provider_call_metrics")
