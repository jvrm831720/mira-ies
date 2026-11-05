"""Sandbox payment proposal foundations. No payment-executing DB objects.

Revision ID: 063_student_payment_preparation
Revises: 062_finance_reconcile
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "063_student_payment_preparation"
down_revision = "062_finance_reconcile"
branch_labels = None
depends_on = None
U = postgresql.UUID(as_uuid=False)
TABLES = ("mira_student_payment_connectors", "mira_student_payment_orders", "mira_student_payment_order_events")


def protect(table):
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(f"""CREATE POLICY {table}_tenant_access ON {table}
      USING (tenant_id = NULLIF(current_setting('app.tenant_id',true),'')::uuid)
      WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id',true),'')::uuid)""")


def upgrade():
    # Parent FK must explicitly include the tenant rather than only the observation UUID.
    op.create_unique_constraint(
        "uq_mira_finance_observation_tenant_id", "mira_finance_observations",
        ["tenant_id", "id"],
    )
    op.create_table("mira_student_payment_connectors",
        sa.Column("id", U, primary_key=True),
        sa.Column("tenant_id", U, sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("provider_slug", sa.String(60), nullable=False, server_default="asaas"),
        sa.Column("destination_wallet_id", U, nullable=False),
        sa.Column("destination_verification_status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("finance_profile_id", U, nullable=False),
        sa.Column("mode", sa.String(12), nullable=False, server_default="sandbox"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("configuration_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", U, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id","id",name="uq_mira_payment_connector_tenant_id"),
        sa.UniqueConstraint("tenant_id","name",name="uq_mira_payment_connector_tenant_name"),
        sa.UniqueConstraint("tenant_id","finance_profile_id","destination_wallet_id",name="uq_mira_payment_finance_destination"),
        sa.ForeignKeyConstraint(["tenant_id","finance_profile_id"],["mira_finance_source_profiles.tenant_id","mira_finance_source_profiles.id"],name="fk_mira_payment_connector_finance_tenant"),
        sa.CheckConstraint("mode = 'sandbox'",name="ck_mira_payment_connector_sandbox"),
        sa.CheckConstraint("provider_slug = 'asaas'",name="ck_mira_payment_connector_asaas"),
        sa.CheckConstraint("destination_verification_status IN ('pending','verified','blocked')",name="ck_mira_payment_destination_status"),
        sa.CheckConstraint("configuration_version > 0",name="ck_mira_payment_connector_version"),
    )
    op.create_index("ix_mira_payment_connector_tenant","mira_student_payment_connectors",["tenant_id","created_at"])
    op.create_table("mira_student_payment_orders",
        sa.Column("id",U,primary_key=True),
        sa.Column("tenant_id",U,sa.ForeignKey("tenants.id"),nullable=False),
        sa.Column("connector_id",U,nullable=False),
        sa.Column("observation_id",U,nullable=False),
        sa.Column("student_id",U,nullable=False),
        sa.Column("amount",sa.Numeric(12,2),nullable=False),
        sa.Column("currency",sa.String(3),nullable=False,server_default="BRL"),
        sa.Column("source_fingerprint",sa.String(64),nullable=False),
        sa.Column("status",sa.String(24),nullable=False,server_default="draft"),
        sa.Column("idempotency_key",sa.String(120),nullable=False),
        sa.Column("requested_by",U,nullable=False),
        sa.Column("approved_by",U),
        sa.Column("approved_at",sa.DateTime(timezone=True)),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id","id",name="uq_mira_payment_order_tenant_id"),
        sa.UniqueConstraint("tenant_id","connector_id","idempotency_key",name="uq_mira_payment_order_idempotency"),
        sa.UniqueConstraint("tenant_id","connector_id","observation_id",name="uq_mira_payment_order_observation_connector"),
        sa.ForeignKeyConstraint(["tenant_id","connector_id"],["mira_student_payment_connectors.tenant_id","mira_student_payment_connectors.id"],name="fk_mira_payment_order_connector_tenant"),
        sa.ForeignKeyConstraint(["tenant_id","observation_id"],["mira_finance_observations.tenant_id","mira_finance_observations.id"],name="fk_mira_payment_order_observation_tenant"),
        sa.ForeignKeyConstraint(["tenant_id","student_id"],["students.tenant_id","students.id"],name="fk_mira_payment_order_student_tenant"),
        sa.CheckConstraint("status IN ('draft','awaiting_approval','approved','cancelled')",name="ck_mira_payment_order_status"),
        sa.CheckConstraint("amount > 0",name="ck_mira_payment_order_amount"),
        sa.CheckConstraint("currency = 'BRL'",name="ck_mira_payment_order_currency"),
    )
    op.create_index("ix_mira_payment_order_tenant_status","mira_student_payment_orders",["tenant_id","status","created_at"])
    op.create_index("ix_mira_payment_order_student","mira_student_payment_orders",["tenant_id","student_id","created_at"])
    op.create_table("mira_student_payment_order_events",
        sa.Column("id",U,primary_key=True),
        sa.Column("tenant_id",U,sa.ForeignKey("tenants.id"),nullable=False),
        sa.Column("order_id",U,nullable=False),
        sa.Column("status",sa.String(24),nullable=False),
        sa.Column("actor_id",U,nullable=False),
        sa.Column("note",sa.Text(),nullable=False),
        sa.Column("occurred_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id","order_id"],["mira_student_payment_orders.tenant_id","mira_student_payment_orders.id"],name="fk_mira_payment_event_order_tenant"),
        sa.CheckConstraint("status IN ('draft','awaiting_approval','approved','cancelled')",name="ck_mira_payment_event_status"),
    )
    op.create_index("ix_mira_payment_event_order","mira_student_payment_order_events",["tenant_id","order_id","occurred_at"])
    for table in TABLES:
        protect(table)
    op.get_bind().exec_driver_sql("""
      CREATE FUNCTION mira_student_payment_event_immutable() RETURNS trigger AS $pay4d$
      BEGIN
        RAISE EXCEPTION 'payment approval history is append-only';
      END;
      $pay4d$ LANGUAGE plpgsql
    """)
    op.execute("""CREATE TRIGGER mira_student_payment_event_immutable
      BEFORE UPDATE OR DELETE ON mira_student_payment_order_events
      FOR EACH ROW EXECUTE FUNCTION mira_student_payment_event_immutable()""")


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS mira_student_payment_event_immutable ON mira_student_payment_order_events")
    op.execute("DROP FUNCTION IF EXISTS mira_student_payment_event_immutable()")
    for table in reversed(TABLES):
        op.drop_table(table)
    op.drop_constraint("uq_mira_finance_observation_tenant_id","mira_finance_observations",type_="unique")
