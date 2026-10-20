"""agents: intervention_logs + student contact fields

Revision ID: 002_agents
Revises: 001_initial
Create Date: 2026-10-21
"""
from typing import Sequence, Union
from alembic import op

revision: str = "002_agents"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
    DO $$ BEGIN
      ALTER TABLE students ADD COLUMN IF NOT EXISTS telefone VARCHAR(30);
      ALTER TABLE students ADD COLUMN IF NOT EXISTS email VARCHAR(255);
    EXCEPTION WHEN undefined_table THEN
      NULL;
    END $$;
    """)
    op.execute("""
    CREATE TABLE IF NOT EXISTS intervention_logs (
        id UUID PRIMARY KEY,
        tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        student_id UUID REFERENCES students(id) ON DELETE SET NULL,
        matricula VARCHAR(50) NOT NULL,
        channel VARCHAR(20),
        risk_level VARCHAR(20),
        risk_score FLOAT,
        template_id VARCHAR(80),
        message_preview VARCHAR(160),
        status VARCHAR(20) NOT NULL,
        skip_reason VARCHAR(120),
        error TEXT,
        provider VARCHAR(40),
        external_id VARCHAR(120),
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)
    op.execute("""
    CREATE INDEX IF NOT EXISTS ix_intervention_logs_tenant_id ON intervention_logs (tenant_id);
    """)
    op.execute("""
    CREATE INDEX IF NOT EXISTS ix_intervention_logs_tenant_student_channel
    ON intervention_logs (tenant_id, student_id, channel, created_at);
    """)
    op.execute("""
    CREATE INDEX IF NOT EXISTS ix_intervention_logs_tenant_status
    ON intervention_logs (tenant_id, status);
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_intervention_logs_tenant_status")
    op.execute("DROP INDEX IF EXISTS ix_intervention_logs_tenant_student_channel")
    op.execute("DROP INDEX IF EXISTS ix_intervention_logs_tenant_id")
    op.execute("DROP TABLE IF EXISTS intervention_logs")
    op.execute("ALTER TABLE students DROP COLUMN IF EXISTS email")
    op.execute("ALTER TABLE students DROP COLUMN IF EXISTS telefone")
