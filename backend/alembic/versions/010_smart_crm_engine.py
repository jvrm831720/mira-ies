"""Smart CRM properties, engagement event history, and dynamic engagement risk adjustment.

Revision ID: 010_smart_crm_engine
Revises: 009_consent_governance_retention
"""
from alembic import op

revision = "010_smart_crm_engine"
down_revision = "009_consent_governance_retention"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE students
            ADD COLUMN IF NOT EXISTS behavior_properties JSONB NOT NULL DEFAULT '{}'::jsonb,
            ADD COLUMN IF NOT EXISTS model_risk_score DOUBLE PRECISION,
            ADD COLUMN IF NOT EXISTS dynamic_risk_adjustment DOUBLE PRECISION NOT NULL DEFAULT 0,
            ADD COLUMN IF NOT EXISTS engagement_score DOUBLE PRECISION,
            ADD COLUMN IF NOT EXISTS engagement_score_updated_at TIMESTAMPTZ
    """)
    # Preserve the existing score as baseline; future interaction-based adjustments remain explainable.
    op.execute("""
        UPDATE students
        SET model_risk_score = risk_score
        WHERE model_risk_score IS NULL AND risk_score IS NOT NULL
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS student_engagement_events (
            id UUID PRIMARY KEY,
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            student_id UUID NOT NULL REFERENCES students(id) ON DELETE CASCADE,
            intervention_log_id UUID REFERENCES intervention_logs(id) ON DELETE SET NULL,
            event_key VARCHAR(200) NOT NULL,
            event_type VARCHAR(30) NOT NULL,
            channel VARCHAR(20),
            source VARCHAR(40) NOT NULL DEFAULT 'system',
            provider VARCHAR(40),
            occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            event_metadata JSONB,
            CONSTRAINT uq_student_engagement_tenant_event_key UNIQUE (tenant_id, event_key)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_student_engagement_tenant_student_time
        ON student_engagement_events (tenant_id, student_id, occurred_at)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_student_engagement_tenant_type_time
        ON student_engagement_events (tenant_id, event_type, occurred_at)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_student_engagement_intervention
        ON student_engagement_events (intervention_log_id)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_student_engagement_intervention")
    op.execute("DROP INDEX IF EXISTS ix_student_engagement_tenant_type_time")
    op.execute("DROP INDEX IF EXISTS ix_student_engagement_tenant_student_time")
    op.execute("DROP TABLE IF EXISTS student_engagement_events")
    op.execute("""
        ALTER TABLE students
        DROP COLUMN IF EXISTS engagement_score_updated_at,
        DROP COLUMN IF EXISTS engagement_score,
        DROP COLUMN IF EXISTS dynamic_risk_adjustment,
        DROP COLUMN IF EXISTS model_risk_score,
        DROP COLUMN IF EXISTS behavior_properties
    """)
