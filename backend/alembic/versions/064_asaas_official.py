"""Wave 4D-B official Asaas payment lifecycle.

Revision ID: 064_asaas_official
Revises: 063_payment_sandbox
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "064_asaas_official"
down_revision = "063_payment_sandbox"
branch_labels = None
depends_on = None

U = UUID(as_uuid=False)
def pk(): return sa.Column("id", U, primary_key=True)
def tenant(): return sa.Column("tenant_id", U, sa.ForeignKey("tenants.id"), nullable=False)
def ref(name): return sa.Column(name, U, nullable=False)
def column(name, limit=80): return sa.Column(name, sa.String(limit), nullable=False)
def unique_tenant(name): return sa.UniqueConstraint("tenant_id", "id", name=name)

def protect(table):
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(f"""CREATE POLICY {table}_tenant_access ON {table}
      USING (tenant_id = NULLIF(current_setting('app.tenant_id', true),'')::uuid)
      WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true),'')::uuid)""")

def upgrade():
    op.add_column("mira_asaas_workspace_destinations",sa.Column("verified_environment",sa.String(16)))
    op.create_table("mira_asaas_customer_bindings",
        pk(), tenant(), ref("student_id"), column("asaas_customer_id"),
        column("issuer_environment",16),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        unique_tenant("uq_mira_asaas_customer_tenant_id"),
        sa.UniqueConstraint("tenant_id","student_id","issuer_environment",name="uq_mira_asaas_customer_student"),
        sa.UniqueConstraint("tenant_id","asaas_customer_id","issuer_environment",name="uq_mira_asaas_customer_external"),
        sa.ForeignKeyConstraint(["tenant_id","student_id"],["students.tenant_id","students.id"],name="fk_mira_asaas_customer_student_tenant"),
        sa.CheckConstraint("issuer_environment IN ('sandbox','production')",name="ck_mira_asaas_customer_environment"))
    op.create_table("mira_asaas_charges",
        pk(),tenant(),ref("financial_observation_id"),ref("student_id"),column("financial_key",64),
        sa.Column("amount",sa.Numeric(12,2),nullable=False),
        column("currency",3),column("method",12),
        sa.Column("due_date",sa.Date(),nullable=False),
        column("customer_id"),ref("destination_wallet_id"),
        sa.Column("destination_version",sa.Integer(),nullable=False),
        column("environment",16),column("external_reference",100),
        sa.Column("asaas_payment_id",sa.String(80)),
        sa.Column("creation_state",sa.String(18),nullable=False,server_default="prepared"),
        sa.Column("provider_payment_status",sa.String(28),nullable=False,server_default="UNKNOWN"),
        sa.Column("provider_split_status",sa.String(28),nullable=False,server_default="UNKNOWN"),
        sa.Column("provider_split_id",sa.String(80)),
        sa.Column("split_configuration_verified",sa.Boolean(),nullable=False,server_default=sa.false()),
        sa.Column("payment_received_verified",sa.Boolean(),nullable=False,server_default=sa.false()),
        sa.Column("split_settled_verified",sa.Boolean(),nullable=False,server_default=sa.false()),
        sa.Column("reconciliation_required",sa.Boolean(),nullable=False,server_default=sa.false()),
        ref("created_by"),sa.Column("authorized_by",U),
        sa.Column("authorized_at",sa.DateTime(timezone=True)),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        unique_tenant("uq_mira_asaas_charge_tenant_id"),
        
        sa.UniqueConstraint("tenant_id","environment","financial_key",name="uq_mira_asaas_charge_financial_key"),
        sa.UniqueConstraint("external_reference",name="uq_mira_asaas_charge_reference"),
        sa.UniqueConstraint("environment","asaas_payment_id",name="uq_mira_asaas_charge_payment_id"),
        sa.ForeignKeyConstraint(["tenant_id","financial_observation_id"],["mira_finance_observations.tenant_id","mira_finance_observations.id"],name="fk_mira_asaas_charge_observation_tenant"),
        sa.ForeignKeyConstraint(["tenant_id","student_id"],["students.tenant_id","students.id"],name="fk_mira_asaas_charge_student_tenant"),
        sa.CheckConstraint("environment IN ('sandbox','production')",name="ck_mira_asaas_charge_environment"),
        sa.CheckConstraint("creation_state IN ('prepared','submitting','unknown','created','rejected','review')",name="ck_mira_asaas_charge_creation"),
        sa.CheckConstraint("amount > 0 AND currency = 'BRL'",name="ck_mira_asaas_charge_amount"),
        sa.CheckConstraint("method IN ('pix','boleto')",name="ck_mira_asaas_charge_method"))
    op.create_index("ix_mira_asaas_charge_tenant_created","mira_asaas_charges",["tenant_id","created_at"])
    op.create_index("ix_mira_asaas_charge_payment_lookup","mira_asaas_charges",["environment","asaas_payment_id"])
    op.create_table("mira_asaas_webhook_events",
        pk(),tenant(),ref("charge_id"),column("environment",16),column("event_id",120),column("event_type"),
        column("payment_id"),sa.Column("split_id",sa.String(100)),
        column("payload_sha256",64),
        sa.Column("received_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        unique_tenant("uq_mira_asaas_event_tenant_id"),
        sa.UniqueConstraint("environment","event_id",name="uq_mira_asaas_event_global_id"),
        sa.ForeignKeyConstraint(["tenant_id","charge_id"],["mira_asaas_charges.tenant_id","mira_asaas_charges.id"],name="fk_mira_asaas_event_charge_tenant"))
    op.create_index("ix_mira_asaas_event_pending","mira_asaas_webhook_events",["tenant_id","received_at"])
    op.create_table("mira_asaas_webhook_applications",
        pk(),tenant(),ref("event_id"),column("outcome",32),column("provider_status",40),
        sa.Column("applied_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id","event_id",name="uq_mira_asaas_applied_event"),
        sa.ForeignKeyConstraint(["tenant_id","event_id"],["mira_asaas_webhook_events.tenant_id","mira_asaas_webhook_events.id"],name="fk_mira_asaas_application_event_tenant"))
    op.create_index("ix_mira_asaas_application_tenant","mira_asaas_webhook_applications",["tenant_id","applied_at"])

    op.create_table("mira_asaas_destination_reviews",pk(),tenant(),
        ref("wallet_id"),sa.Column("wallet_version",sa.Integer(),nullable=False),
        column("issuer_environment",16),ref("reviewer_id"),column("reference_sha256",64),
        sa.Column("reviewed_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id","wallet_id","wallet_version","issuer_environment",
            name="uq_mira_asaas_destination_review_version"))
    op.create_index("ix_mira_asaas_destination_review_tenant","mira_asaas_destination_reviews",["tenant_id","reviewed_at"])
    for name in ("mira_asaas_customer_bindings","mira_asaas_charges","mira_asaas_webhook_events","mira_asaas_webhook_applications","mira_asaas_destination_reviews"):
        protect(name)
    # Shared issuing-account callback; allow lookup ONLY in token-verified transaction.
    op.execute("""CREATE POLICY mira_asaas_charges_webhook_lookup
      ON mira_asaas_charges FOR SELECT
      USING (current_setting('app.asaas_webhook_authenticated',true)='yes')""")
    op.get_bind().exec_driver_sql("""
      CREATE FUNCTION mira_asaas_resolve_payment(p_id text)
      RETURNS TABLE(resolved_tenant uuid, resolved_charge uuid)
      LANGUAGE sql SECURITY DEFINER SET search_path=public,pg_temp AS $asaas$
        SELECT c.tenant_id,c.id FROM public.mira_asaas_charges c
        WHERE current_setting('app.asaas_webhook_authenticated',true)='yes'
          AND c.environment=current_setting('app.asaas_webhook_environment',true)
          AND length(p_id) BETWEEN 6 AND 80 AND c.asaas_payment_id=p_id LIMIT 1
      $asaas$
    """)
    op.get_bind().exec_driver_sql("""
      CREATE FUNCTION mira_asaas_history_immutable() RETURNS trigger
      LANGUAGE plpgsql AS $audit$
      BEGIN RAISE EXCEPTION 'Asaas webhook history is append-only'; END
      $audit$
    """)
    for name in ("mira_asaas_webhook_events","mira_asaas_webhook_applications","mira_asaas_destination_reviews"):
        op.execute(f"""CREATE TRIGGER {name}_immutable BEFORE UPDATE OR DELETE ON {name}
          FOR EACH ROW EXECUTE FUNCTION mira_asaas_history_immutable()""")

def downgrade():
    for name in ("mira_asaas_webhook_events","mira_asaas_webhook_applications","mira_asaas_destination_reviews"):
        op.execute(f"DROP TRIGGER IF EXISTS {name}_immutable ON {name}")
    op.execute("DROP FUNCTION IF EXISTS mira_asaas_history_immutable()")
    op.execute("DROP FUNCTION IF EXISTS mira_asaas_resolve_payment(text)")
    for name in ("mira_asaas_destination_reviews","mira_asaas_webhook_applications","mira_asaas_webhook_events","mira_asaas_charges","mira_asaas_customer_bindings"):
        op.drop_table(name)
    op.drop_column("mira_asaas_workspace_destinations","verified_environment")
