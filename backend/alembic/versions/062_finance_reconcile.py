"""Metadata-defined multi-source financial reconciliation (no payment execution).

Revision ID: 062_finance_reconcile
Revises: 061_student_document_attestation
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "062_finance_reconcile"
down_revision = "061_student_document_attestation"
branch_labels = None
depends_on = None
U = postgresql.UUID(as_uuid=False)
J = postgresql.JSONB
TABLES = (
    "mira_finance_source_profiles",
    "mira_finance_student_links",
    "mira_finance_ingestion_batches",
    "mira_finance_observations",
    "mira_finance_review_cases",
    "mira_finance_review_events",
)


def identifier():
    return sa.Column("id", U, primary_key=True)


def tenant():
    return sa.Column("tenant_id", U, sa.ForeignKey("tenants.id"), nullable=False)


def reference(name):
    return sa.Column(name, U, nullable=False)


def fk_profile(name):
    return sa.ForeignKeyConstraint(
        ["tenant_id", name],
        ["mira_finance_source_profiles.tenant_id", "mira_finance_source_profiles.id"],
        name="fk_mira_finance_" + name + "_tenant",
    )


def protect(table):
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(f"""CREATE POLICY {table}_tenant_access ON {table}
        USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)""")


def upgrade():
    op.create_table(
        "mira_finance_source_profiles",
        identifier(), tenant(),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("source_kind", sa.String(20), nullable=False),
        sa.Column("connected_account_id", sa.String(120)),
        sa.Column("tool_slug", sa.String(120)),
        sa.Column("rows_path", sa.String(240), nullable=False, server_default=""),
        sa.Column("field_map", J, nullable=False),
        sa.Column("status_map", J, nullable=False),
        sa.Column("review_workflow", J, nullable=False),
        sa.Column("student_lookup", sa.String(20), nullable=False, server_default="mira_id"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("mapping_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", U, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "id", name="uq_mira_finance_profile_tenant_id"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_mira_finance_profile_tenant_name"),
        sa.CheckConstraint("source_kind IN ('composio','import')", name="ck_mira_finance_profile_kind"),
        sa.CheckConstraint("mapping_version > 0", name="ck_mira_finance_mapping_version"),
    )
    op.create_index("ix_mira_finance_profiles_tenant_kind", "mira_finance_source_profiles", ["tenant_id", "source_kind"])

    op.create_table(
        "mira_finance_student_links",
        identifier(), tenant(), reference("profile_id"),
        sa.Column("external_student_ref", sa.String(120), nullable=False),
        reference("student_id"), sa.Column("verified_by", U, nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "profile_id", "external_student_ref", name="uq_mira_finance_student_source_ref"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "profile_id"], ["mira_finance_source_profiles.tenant_id", "mira_finance_source_profiles.id"],
            name="fk_mira_finance_link_profile_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "student_id"], ["students.tenant_id", "students.id"],
            name="fk_mira_finance_link_student_tenant",
        ),
    )
    op.create_index("ix_mira_finance_link_student", "mira_finance_student_links", ["tenant_id", "student_id"])

    op.create_table(
        "mira_finance_ingestion_batches",
        identifier(), tenant(), reference("profile_id"),
        sa.Column("actor_id", U, nullable=False),
        sa.Column("origin", sa.String(20), nullable=False),
        sa.Column("idempotency_key", sa.String(120), nullable=False),
        sa.Column("payload_digest", sa.String(64), nullable=False),
        sa.Column("mapping_version", sa.Integer(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("imported_count", sa.Integer(), nullable=False),
        sa.Column("unchanged_count", sa.Integer(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "id", name="uq_mira_finance_batch_tenant_id"),
        sa.UniqueConstraint("tenant_id", "profile_id", "idempotency_key", name="uq_mira_finance_batch_idempotency"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "profile_id"], ["mira_finance_source_profiles.tenant_id", "mira_finance_source_profiles.id"],
            name="fk_mira_finance_batch_profile_tenant",
        ),
        sa.CheckConstraint("row_count >= 0 AND row_count <= 100", name="ck_mira_finance_batch_row_count"),
    )

    op.create_table(
        "mira_finance_observations",
        identifier(), tenant(), reference("profile_id"),
        reference("student_id"), reference("batch_id"),
        sa.Column("external_id", sa.String(120), nullable=False),
        sa.Column("correlation_key", sa.String(120)),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("label", sa.String(180), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("paid_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True)),
        sa.Column("source_updated_at", sa.DateTime(timezone=True)),
        sa.Column("canonical_state", sa.String(20), nullable=False),
        sa.Column("raw_status", sa.String(50), nullable=False),
        sa.Column("mapping_version", sa.Integer(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "profile_id", "fingerprint", name="uq_mira_finance_observation_dedup"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "profile_id"], ["mira_finance_source_profiles.tenant_id", "mira_finance_source_profiles.id"],
            name="fk_mira_finance_obs_profile_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "student_id"], ["students.tenant_id", "students.id"],
            name="fk_mira_finance_obs_student_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "batch_id"], ["mira_finance_ingestion_batches.tenant_id", "mira_finance_ingestion_batches.id"],
            name="fk_mira_finance_obs_batch_tenant",
        ),
        sa.CheckConstraint("amount >= 0 AND paid_amount >= 0 AND paid_amount <= amount", name="ck_mira_finance_obs_amounts"),
        sa.CheckConstraint(
            "canonical_state IN ('open','overdue','partially_paid','reported_paid','cancelled','disputed','unknown')",
            name="ck_mira_finance_obs_state",
        ),
    )
    op.create_index("ix_mira_finance_obs_reconciliation", "mira_finance_observations", ["tenant_id", "student_id", "correlation_key"])
    op.create_index("ix_mira_finance_obs_source", "mira_finance_observations", ["tenant_id", "profile_id", "external_id", "observed_at"])

    op.create_table(
        "mira_finance_review_cases",
        identifier(), tenant(), reference("profile_id"),
        sa.Column("external_id", sa.String(120), nullable=False),
        sa.Column("step", sa.String(24), nullable=False, server_default="open"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", U, nullable=False), sa.Column("updated_by", U, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "id", name="uq_mira_finance_case_tenant_id"),
        sa.UniqueConstraint("tenant_id", "profile_id", "external_id", name="uq_mira_finance_case_source"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "profile_id"], ["mira_finance_source_profiles.tenant_id", "mira_finance_source_profiles.id"],
            name="fk_mira_finance_case_profile_tenant",
        ),
        sa.CheckConstraint("step ~ '^[a-z][a-z0-9_]{0,23}$'", name="ck_mira_finance_case_step"),
    )
    op.create_index("ix_mira_finance_case_tenant_step", "mira_finance_review_cases", ["tenant_id", "step"])

    op.create_table(
        "mira_finance_review_events",
        identifier(), tenant(), reference("case_id"),
        sa.Column("step", sa.String(24), nullable=False), sa.Column("actor_id", U, nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["tenant_id", "case_id"], ["mira_finance_review_cases.tenant_id", "mira_finance_review_cases.id"],
            name="fk_mira_finance_review_case_tenant",
        ),
    )
    op.create_index("ix_mira_finance_review_history", "mira_finance_review_events", ["tenant_id", "case_id", "recorded_at"])

    for table in TABLES:
        protect(table)

    # Only observation, batch and review-event history is immutable; review cases
    # and source mapping profiles are versioned configurations.
    op.get_bind().exec_driver_sql("""
        CREATE FUNCTION mira_finance_history_immutable() RETURNS trigger AS $wave4c$
        BEGIN
            RAISE EXCEPTION 'financial ingestion history is append-only';
        END;
        $wave4c$ LANGUAGE plpgsql
    """)
    for table in ("mira_finance_ingestion_batches", "mira_finance_observations", "mira_finance_review_events"):
        op.execute(f"""CREATE TRIGGER {table}_immutable
            BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION mira_finance_history_immutable()""")


def downgrade():
    for table in ("mira_finance_ingestion_batches", "mira_finance_observations", "mira_finance_review_events"):
        op.execute(f"DROP TRIGGER IF EXISTS {table}_immutable ON {table}")
    op.execute("DROP FUNCTION IF EXISTS mira_finance_history_immutable()")
    for table in reversed(TABLES):
        op.drop_table(table)
", name="ck_mira_finance_case_step"),
    )
    op.create_index("ix_mira_finance_case_tenant_step", "mira_finance_review_cases", ["tenant_id", "step"])

    op.create_table(
        "mira_finance_review_events",
        identifier(), tenant(), reference("case_id"),
        sa.Column("step", sa.String(24), nullable=False), sa.Column("actor_id", U, nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["tenant_id", "case_id"], ["mira_finance_review_cases.tenant_id", "mira_finance_review_cases.id"],
            name="fk_mira_finance_review_case_tenant",
        ),
    )
    op.create_index("ix_mira_finance_review_history", "mira_finance_review_events", ["tenant_id", "case_id", "recorded_at"])

    for table in TABLES:
        protect(table)

    # Only observation, batch and review-event history is immutable; review cases
    # and source mapping profiles are versioned configurations.
    op.get_bind().exec_driver_sql("""
        CREATE FUNCTION mira_finance_history_immutable() RETURNS trigger AS $wave4c$
        BEGIN
            RAISE EXCEPTION 'financial ingestion history is append-only';
        END;
        $wave4c$ LANGUAGE plpgsql
    """)
    for table in ("mira_finance_ingestion_batches", "mira_finance_observations", "mira_finance_review_events"):
        op.execute(f"""CREATE TRIGGER {table}_immutable
            BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION mira_finance_history_immutable()""")


def downgrade():
    for table in ("mira_finance_ingestion_batches", "mira_finance_observations", "mira_finance_review_events"):
        op.execute(f"DROP TRIGGER IF EXISTS {table}_immutable ON {table}")
    op.execute("DROP FUNCTION IF EXISTS mira_finance_history_immutable()")
    for table in reversed(TABLES):
        op.drop_table(table)
