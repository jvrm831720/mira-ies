"""Manual billing records for MIRA Control Center.

Revision ID: 013_control_center_billing
Revises: 012_control_center_admin
"""
from alembic import op

revision = "013_control_center_billing"
down_revision = "012_control_center_admin"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS mira_control_billing_records (
            id UUID PRIMARY KEY,
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            created_by_admin_id UUID REFERENCES mira_control_admins(id) ON DELETE SET NULL,
            plan_name VARCHAR(120) NOT NULL,
            plan_price_brl NUMERIC(12, 2) NOT NULL,
            billing_cycle VARCHAR(16) NOT NULL DEFAULT 'monthly',
            payment_link VARCHAR(500),
            due_at TIMESTAMPTZ NOT NULL,
            plan_status VARCHAR(16) NOT NULL DEFAULT 'active',
            payment_status VARCHAR(16) NOT NULL DEFAULT 'pending',
            notes VARCHAR(500),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_mira_control_billing_tenant UNIQUE (tenant_id),
            CONSTRAINT ck_mira_control_billing_cycle CHECK (billing_cycle IN ('monthly', 'yearly')),
            CONSTRAINT ck_mira_control_billing_plan_status CHECK (plan_status IN ('active', 'paused', 'cancelled')),
            CONSTRAINT ck_mira_control_billing_payment_status CHECK (payment_status IN ('pending', 'paid'))
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_mira_control_billing_due
        ON mira_control_billing_records (payment_status, due_at)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_mira_control_billing_due")
    op.execute("DROP TABLE IF EXISTS mira_control_billing_records")
