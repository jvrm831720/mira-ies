"""Student requests, event history, published documents and read-only financial references.

Revision ID: 058_student_services
Revises: 057_native_academic_catalog
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "058_student_services"
down_revision = "057_native_academic_catalog"
branch_labels = None
depends_on = None
U = postgresql.UUID(as_uuid=False)
TABLES = ("mira_student_service_requests", "mira_student_service_events", "mira_student_documents", "mira_student_financial_references")


def tenant(name):
    return sa.Column(name, U, sa.ForeignKey("tenants.id"), nullable=False)


def reference(name):
    return sa.Column(name, U, nullable=False)


def relation(local, target, target_col, constraint):
    return sa.ForeignKeyConstraint(["tenant_id", local], [target + ".tenant_id", target + "." + target_col], name=constraint)


def protect(name):
    op.execute(f"ALTER TABLE {name} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {name} FORCE ROW LEVEL SECURITY")
    op.execute(f"""CREATE POLICY {name}_tenant_access ON {name}
        USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)""")


def upgrade():
    op.create_table("mira_student_service_requests",
        sa.Column("id", U, primary_key=True), tenant("tenant_id"), reference("student_id"),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("subject", sa.String(180), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="submitted"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "id", name="uq_mira_service_request_tenant_id"),
        relation("student_id", "students", "id", "fk_mira_request_student_tenant"),
        sa.CheckConstraint("status IN ('submitted','in_review','approved','rejected','completed','cancelled')", name="ck_mira_service_request_status"))
    op.create_index("ix_mira_service_request_student", "mira_student_service_requests", ["tenant_id", "student_id", "created_at"])
    op.create_table("mira_student_service_events",
        sa.Column("id", U, primary_key=True), tenant("tenant_id"), reference("request_id"),
        sa.Column("actor_type", sa.String(20), nullable=False),
        sa.Column("actor_user_id", U),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("note", sa.String(500)),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        relation("request_id", "mira_student_service_requests", "id", "fk_mira_service_event_request_tenant"))
    op.create_index("ix_mira_service_event_request", "mira_student_service_events", ["tenant_id", "request_id", "occurred_at"])
    op.create_table("mira_student_documents",
        sa.Column("id", U, primary_key=True), tenant("tenant_id"), reference("student_id"),
        sa.Column("kind", sa.String(50), nullable=False),
        sa.Column("title", sa.String(180), nullable=False),
        sa.Column("content_text", sa.Text(), nullable=False),
        sa.Column("publication_status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        relation("student_id", "students", "id", "fk_mira_document_student_tenant"),
        sa.CheckConstraint("publication_status IN ('draft','published','revoked')", name="ck_mira_document_publication"))
    op.create_index("ix_mira_document_student", "mira_student_documents", ["tenant_id", "student_id", "created_at"])
    op.create_table("mira_student_financial_references",
        sa.Column("id", U, primary_key=True), tenant("tenant_id"), reference("student_id"),
        sa.Column("source", sa.String(60), nullable=False),
        sa.Column("external_id", sa.String(120), nullable=False),
        sa.Column("label", sa.String(180), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="BRL"),
        sa.Column("due_on", sa.DateTime(timezone=True)),
        sa.Column("source_status", sa.String(50), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        relation("student_id", "students", "id", "fk_mira_financial_reference_student_tenant"),
        sa.UniqueConstraint("tenant_id", "student_id", "source", "external_id", name="uq_mira_financial_reference_source"),
        sa.CheckConstraint("amount >= 0", name="ck_mira_financial_reference_amount"))
    op.create_index("ix_mira_financial_reference_student", "mira_student_financial_references", ["tenant_id", "student_id"])
    for table in TABLES:
        protect(table)
    # Database-level append-only audit history for student requests.
    op.execute("""
        CREATE FUNCTION mira_service_event_immutable() RETURNS trigger AS $
        BEGIN
            RAISE EXCEPTION 'student service history is append-only';
        END;
        $ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER mira_student_service_event_immutable
        BEFORE UPDATE OR DELETE ON mira_student_service_events
        FOR EACH ROW EXECUTE FUNCTION mira_service_event_immutable()
    """)


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS mira_student_service_event_immutable ON mira_student_service_events")
    op.execute("DROP FUNCTION IF EXISTS mira_service_event_immutable()")
    for table in reversed(TABLES):
        op.drop_table(table)
