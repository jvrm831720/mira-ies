"""Student document integrity attestation (not legal signature service).

Revision ID: 061_student_document_attestation
Revises: 060_student_finance_composio
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "061_student_document_attestation"
down_revision = "060_student_finance_composio"
branch_labels = None
depends_on = None
U = postgresql.UUID(as_uuid=False)


def upgrade():
    op.create_unique_constraint(
        "uq_mira_student_document_tenant_id", "mira_student_documents", ["tenant_id", "id"],
    )
    op.create_table(
        "mira_student_document_attestations",
        sa.Column("id", U, primary_key=True),
        sa.Column("tenant_id", U, sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("document_id", U, nullable=False),
        sa.Column("student_id", U, nullable=False),
        sa.Column("issued_by_user_id", U, sa.ForeignKey("mira_users.id"), nullable=False),
        sa.Column("signing_key_id", sa.String(40), nullable=False),
        sa.Column("content_digest", sa.String(64), nullable=False),
        sa.Column("signature", sa.String(64), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_by_user_id", U),
        sa.UniqueConstraint("tenant_id", "id", name="uq_student_attestation_tenant_id"),
        sa.UniqueConstraint("tenant_id", "document_id", name="uq_student_attestation_document"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["mira_student_documents.tenant_id", "mira_student_documents.id"],
            name="fk_student_attestation_document_tenant",
        ),
    )
    op.create_index("ix_student_attestation_document", "mira_student_document_attestations", ["tenant_id", "document_id"])
    op.execute("ALTER TABLE mira_student_document_attestations ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE mira_student_document_attestations FORCE ROW LEVEL SECURITY")
    op.execute("""CREATE POLICY mira_student_document_attestations_tenant_access
        ON mira_student_document_attestations
        USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)""")
    op.get_bind().exec_driver_sql("""
        CREATE FUNCTION mira_student_document_attestation_guard() RETURNS trigger AS $wave4doc$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'attestation deletion forbidden';
            END IF;
            IF OLD.revoked_at IS NOT NULL
               OR NEW.revoked_at IS NULL OR NEW.revoked_by_user_id IS NULL
               OR NEW.id IS DISTINCT FROM OLD.id
               OR NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
               OR NEW.document_id IS DISTINCT FROM OLD.document_id
               OR NEW.student_id IS DISTINCT FROM OLD.student_id
               OR NEW.issued_by_user_id IS DISTINCT FROM OLD.issued_by_user_id
               OR NEW.signing_key_id IS DISTINCT FROM OLD.signing_key_id
               OR NEW.content_digest IS DISTINCT FROM OLD.content_digest
               OR NEW.signature IS DISTINCT FROM OLD.signature
               OR NEW.issued_at IS DISTINCT FROM OLD.issued_at THEN
                RAISE EXCEPTION 'attestation can only be revoked once';
            END IF;
            RETURN NEW;
        END;
        $wave4doc$ LANGUAGE plpgsql
    """)
    op.execute("""CREATE TRIGGER mira_student_document_attestation_guard
        BEFORE UPDATE OR DELETE ON mira_student_document_attestations
        FOR EACH ROW EXECUTE FUNCTION mira_student_document_attestation_guard()""")


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS mira_student_document_attestation_guard ON mira_student_document_attestations")
    op.execute("DROP FUNCTION IF EXISTS mira_student_document_attestation_guard()")
    op.drop_table("mira_student_document_attestations")
    op.drop_constraint("uq_mira_student_document_tenant_id", "mira_student_documents", type_="unique")
