"""Eligible contributions registry for shared MIRA Base training.

Revision ID: 041_eligible_contributions
Revises: 040_governance_policy_hardening
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "041_eligible_contributions"
down_revision = "040_governance_policy_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "eligible_contributions",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("contribution_key", sa.String(128), nullable=False),
        sa.Column("source_dataset_ref", sa.String(500), nullable=False),
        sa.Column("policy_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("policy_contract_version", sa.String(80), nullable=False),
        sa.Column("modality", sa.String(32), nullable=False),
        sa.Column("eligibility_status", sa.String(32), nullable=False),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("approval_reason", sa.Text(), nullable=True),
        sa.Column("sanitized_content_hash", sa.String(128), nullable=False),
        sa.Column("anonymization_rules_version", sa.String(40), nullable=False),
        sa.Column("feature_schema_version", sa.String(40), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("assessed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("assessed_by_admin_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("mira_control_admins.id", ondelete="SET NULL"), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "modality IN ('shared_training', 'institution_only')",
            name="ck_eligible_contributions_modality",
        ),
        sa.CheckConstraint(
            "eligibility_status IN ('eligible', 'rejected', 'revoked')",
            name="ck_eligible_contributions_status",
        ),
        sa.UniqueConstraint(
            "tenant_id", "contribution_key", "sanitized_content_hash",
            name="uq_eligible_contributions_idempotent",
        ),
    )
    op.create_index(
        "ix_eligible_contributions_tenant_status",
        "eligible_contributions",
        ["tenant_id", "eligibility_status"],
    )
    op.create_index(
        "ix_eligible_contributions_tenant_assessed",
        "eligible_contributions",
        ["tenant_id", "assessed_at"],
    )
    op.create_index(
        "ix_eligible_contributions_hash",
        "eligible_contributions",
        ["sanitized_content_hash"],
    )

    # FORCE RLS + tenant isolation (admin context allowed)
    op.execute("ALTER TABLE eligible_contributions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE eligible_contributions FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY eligible_contributions_tenant_isolation ON eligible_contributions
        FOR ALL
        USING (
            tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
            OR current_setting('app.is_mira_admin', true) = 'true'
        )
        WITH CHECK (
            tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
            OR current_setting('app.is_mira_admin', true) = 'true'
        )
        """
    )

    # Append-only history (revocation = new status via service, not UPDATE/DELETE)
    op.execute(
        """
        CREATE OR REPLACE FUNCTION reject_eligible_contributions_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $contrib$
        BEGIN
            IF pg_trigger_depth() > 1 THEN
                IF TG_OP = 'DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
            END IF;
            RAISE EXCEPTION 'eligible_contributions history is append-only';
        END;
        $contrib$
        """
    )
    op.execute(
        "CREATE TRIGGER trg_eligible_contributions_append_only "
        "BEFORE UPDATE OR DELETE ON eligible_contributions "
        "FOR EACH ROW EXECUTE FUNCTION reject_eligible_contributions_mutation()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_eligible_contributions_append_only ON eligible_contributions")
    op.execute("DROP FUNCTION IF EXISTS reject_eligible_contributions_mutation()")
    op.execute("DROP POLICY IF EXISTS eligible_contributions_tenant_isolation ON eligible_contributions")
    op.execute("ALTER TABLE eligible_contributions NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE eligible_contributions DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_eligible_contributions_hash", table_name="eligible_contributions")
    op.drop_index("ix_eligible_contributions_tenant_assessed", table_name="eligible_contributions")
    op.drop_index("ix_eligible_contributions_tenant_status", table_name="eligible_contributions")
    op.drop_table("eligible_contributions")
