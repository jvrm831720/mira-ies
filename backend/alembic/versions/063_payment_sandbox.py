"""Wave 4D-A: sandbox-only payment drafts and provider evidence.

Revision ID: 063_payment_sandbox
Revises: 062_finance_reconcile
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "063_payment_sandbox"
down_revision = "062_finance_reconcile"
branch_labels = None
depends_on = None
U = postgresql.UUID(as_uuid=False)

TABLES = (
    "mira_asaas_workspace_destinations",
    "mira_payment_provider_profiles",
    "mira_student_payment_intents",
    "mira_student_payment_evidence",
)


def pk():
    return sa.Column("id", U, primary_key=True)


def tenant():
    return sa.Column("tenant_id", U, sa.ForeignKey("tenants.id"), nullable=False)


def protection(table):
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(f"""CREATE POLICY {table}_tenant_access ON {table}
        USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)""")


def upgrade():
    op.create_table(
        "mira_asaas_workspace_destinations",
        pk(), tenant(),
        sa.Column("wallet_id", U, nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("confirmed_by_user_id", U, nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.Column("verified_by_user_id", U),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", name="uq_mira_asaas_destination_tenant"),
        sa.CheckConstraint("status IN ('pending','verified','rejected')", name="ck_mira_asaas_destination_status"),
        sa.CheckConstraint("version >= 1", name="ck_mira_asaas_destination_version"),
    )
    op.create_unique_constraint(
        "uq_mira_finance_observation_tenant_id",
        "mira_finance_observations", ["tenant_id", "id"],
    )
    op.create_table(
        "mira_payment_provider_profiles",
        pk(), tenant(),
        sa.Column("finance_profile_id", U, nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("connection_kind", sa.String(24), nullable=False),
        sa.Column("connected_account_id", sa.String(120)),
        sa.Column("provider_slug", sa.String(80), nullable=False),
        sa.Column("methods", postgresql.JSONB, nullable=False),
        sa.Column("environment", sa.String(12), nullable=False, server_default="sandbox"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", U, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "id", name="uq_mira_pay_provider_tenant_id"),
        sa.UniqueConstraint("tenant_id", "finance_profile_id", "name", name="uq_mira_pay_provider_name"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "finance_profile_id"],
            ["mira_finance_source_profiles.tenant_id", "mira_finance_source_profiles.id"],
            name="fk_mira_pay_provider_source_tenant",
        ),
        sa.CheckConstraint("connection_kind IN ('composio','custom_pending')", name="ck_mira_pay_provider_kind"),
        sa.CheckConstraint("environment = 'sandbox'", name="ck_mira_pay_provider_sandbox"),
    )
    op.create_index("ix_mira_pay_provider_source", "mira_payment_provider_profiles", ["tenant_id", "finance_profile_id"])

    op.create_table(
        "mira_student_payment_intents",
        pk(), tenant(),
        sa.Column("provider_id", U, nullable=False),
        sa.Column("financial_observation_id", U, nullable=False),
        sa.Column("student_id", U, nullable=False),
        sa.Column("method", sa.String(16), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="BRL"),
        sa.Column("idempotency_key", sa.String(120), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("created_by", U, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "id", name="uq_mira_pay_intent_tenant_id"),
        sa.UniqueConstraint("tenant_id", "provider_id", "id", name="uq_mira_pay_intent_provider_id"),
        sa.UniqueConstraint("tenant_id", "provider_id", "idempotency_key", name="uq_mira_pay_intent_idempotency"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "provider_id"],
            ["mira_payment_provider_profiles.tenant_id", "mira_payment_provider_profiles.id"],
            name="fk_mira_pay_intent_provider_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "student_id"], ["students.tenant_id", "students.id"],
            name="fk_mira_pay_intent_student_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "financial_observation_id"],
            ["mira_finance_observations.tenant_id", "mira_finance_observations.id"],
            name="fk_mira_pay_intent_observation_tenant",
        ),
        sa.CheckConstraint("amount > 0 AND amount <= 9999999999.99", name="ck_mira_pay_intent_amount"),
        sa.CheckConstraint("currency = 'BRL'", name="ck_mira_pay_intent_currency"),
        sa.CheckConstraint("status = 'draft'", name="ck_mira_pay_intent_draft"),
    )
    op.create_index("ix_mira_pay_intents_student", "mira_student_payment_intents", ["tenant_id", "student_id", "created_at"])

    op.create_table(
        "mira_student_payment_evidence",
        pk(), tenant(),
        sa.Column("provider_id", U, nullable=False),
        sa.Column("intent_id", U, nullable=False),
        sa.Column("provider_event_id", sa.String(120), nullable=False),
        sa.Column("reported_state", sa.String(32), nullable=False),
        sa.Column("reported_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("signature_type", sa.String(40), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "provider_id", "provider_event_id", name="uq_mira_pay_event_id"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "provider_id", "intent_id"],
            ["mira_student_payment_intents.tenant_id", "mira_student_payment_intents.provider_id", "mira_student_payment_intents.id"],
            name="fk_mira_pay_evidence_intent_provider_tenant",
        ),
        sa.CheckConstraint(
            "reported_state IN ('created','processing','partially_paid_reported','paid_reported','failed','refunded_reported','chargeback_reported')",
            name="ck_mira_pay_evidence_state",
        ),
        sa.CheckConstraint("reported_amount >= 0", name="ck_mira_pay_evidence_amount"),
        sa.CheckConstraint("currency = 'BRL'", name="ck_mira_pay_evidence_currency"),
    )
    op.create_index("ix_mira_pay_evidence_intent", "mira_student_payment_evidence", ["tenant_id", "intent_id", "received_at"])
    for table in TABLES:
        protection(table)
    op.get_bind().exec_driver_sql("""
        CREATE FUNCTION mira_payment_history_immutable() RETURNS trigger AS $payment4d$
        BEGIN
            RAISE EXCEPTION 'payment drafts and evidence are append-only';
        END;
        $payment4d$ LANGUAGE plpgsql
    """)
    for table in ("mira_student_payment_intents", "mira_student_payment_evidence"):
        op.execute(f"""CREATE TRIGGER {table}_immutable
            BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION mira_payment_history_immutable()""")


def downgrade():
    for table in ("mira_student_payment_intents", "mira_student_payment_evidence"):
        op.execute(f"DROP TRIGGER IF EXISTS {table}_immutable ON {table}")
    op.execute("DROP FUNCTION IF EXISTS mira_payment_history_immutable()")
    for table in reversed(TABLES):
        op.drop_table(table)
    op.drop_constraint("uq_mira_finance_observation_tenant_id", "mira_finance_observations", type_="unique")
