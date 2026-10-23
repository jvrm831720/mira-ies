"""Granular communication preferences, consent trail and intervention log TTL.

Revision ID: 009_consent_governance_retention
Revises: 008_retention_active_version
"""
from alembic import op

revision = "009_consent_governance_retention"
down_revision = "008_retention_active_version"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE students
        ADD COLUMN IF NOT EXISTS communication_preferences JSONB NOT NULL
        DEFAULT '{"channels":{"whatsapp":true,"email":true,"sms":true},
                   "topics":{"academic":true,"retention":true,"promotional":false}}'::jsonb
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS consent_audit_events (
            id UUID PRIMARY KEY,
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            student_id UUID REFERENCES students(id) ON DELETE SET NULL,
            student_matricula VARCHAR(50) NOT NULL,
            event_type VARCHAR(60) NOT NULL,
            channel VARCHAR(20),
            topic VARCHAR(40),
            previous_value JSONB,
            new_value JSONB,
            source VARCHAR(40) NOT NULL,
            method VARCHAR(60) NOT NULL,
            location VARCHAR(120) NOT NULL,
            source_reference VARCHAR(160),
            actor_user_id VARCHAR(36),
            occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            notes TEXT
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_consent_audit_tenant_student_time
        ON consent_audit_events (tenant_id, student_id, occurred_at)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_consent_audit_tenant_time
        ON consent_audit_events (tenant_id, occurred_at)
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS intervention_log_daily_aggregates (
            id UUID PRIMARY KEY,
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            metric_date DATE NOT NULL,
            status VARCHAR(20) NOT NULL,
            channel_bucket VARCHAR(20) NOT NULL DEFAULT '_none',
            risk_level_bucket VARCHAR(20) NOT NULL DEFAULT '_none',
            outcome_bucket VARCHAR(40) NOT NULL DEFAULT '_none',
            event_count INTEGER NOT NULL DEFAULT 0,
            aggregated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_intervention_log_daily_aggregate_key
                UNIQUE (tenant_id, metric_date, status, channel_bucket, risk_level_bucket, outcome_bucket)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_intervention_aggregate_tenant_date
        ON intervention_log_daily_aggregates (tenant_id, metric_date)
    """)
    op.execute("""
        UPDATE students
        SET communication_opted_out_at = COALESCE(communication_opted_out_at, updated_at, created_at)
        WHERE communication_opt_out IS TRUE
    """)


def downgrade() -> None:
    # Agregados e trilha de consentimento são dados de governança. Antes de remover
    # essas tabelas em produção, exporte/retencione o material requerido pela política.
    op.execute("DROP INDEX IF EXISTS ix_intervention_aggregate_tenant_date")
    op.execute("DROP TABLE IF EXISTS intervention_log_daily_aggregates")
    op.execute("DROP INDEX IF EXISTS ix_consent_audit_tenant_time")
    op.execute("DROP INDEX IF EXISTS ix_consent_audit_tenant_student_time")
    op.execute("DROP TABLE IF EXISTS consent_audit_events")
    op.execute("ALTER TABLE students DROP COLUMN IF EXISTS communication_preferences")
