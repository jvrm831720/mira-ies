"""Wave 5: institutional academic service workflow, immutable conversation and evidence.

Revision ID: 064_academic_services_central
Revises: 064_asaas_official
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "064_academic_services_central"
down_revision = "064_asaas_official"
branch_labels = None
depends_on = None
U = postgresql.UUID(as_uuid=False)
TABLES = (
    "mira_student_service_comments",
    "mira_student_service_attachments",
    "mira_student_service_notifications",
    "mira_student_document_templates",
)


def _rls(name):
    op.execute(f"ALTER TABLE {name} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {name} FORCE ROW LEVEL SECURITY")
    op.execute(f"""CREATE POLICY {name}_tenant_access ON {name}
        USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)""")


def _tenant():
    return sa.Column("tenant_id", U, sa.ForeignKey("tenants.id"), nullable=False)


def _request_fk(name):
    return sa.ForeignKeyConstraint(
        ["tenant_id", "request_id"],
        ["mira_student_service_requests.tenant_id", "mira_student_service_requests.id"],
        name=name,
    )


def upgrade():
    op.create_unique_constraint(
        "uq_mira_memberships_tenant_id_id", "mira_memberships", ["tenant_id", "id"],
    )
    op.add_column("mira_student_service_requests", sa.Column("assigned_membership_id", U))
    op.add_column("mira_student_service_requests", sa.Column("assigned_at", sa.DateTime(timezone=True)))
    op.add_column("mira_student_service_requests", sa.Column("due_at", sa.DateTime(timezone=True)))
    op.add_column("mira_student_service_requests", sa.Column("priority", sa.String(12), nullable=False, server_default="normal"))
    op.add_column("mira_student_service_requests", sa.Column("completed_at", sa.DateTime(timezone=True)))
    op.add_column("mira_student_service_requests", sa.Column("generated_document_id", U))
    op.create_foreign_key(
        "fk_mira_service_assignee_membership_tenant", "mira_student_service_requests",
        "mira_memberships", ["tenant_id", "assigned_membership_id"], ["tenant_id", "id"],
    )
    op.create_foreign_key(
        "fk_mira_service_generated_document_tenant", "mira_student_service_requests",
        "mira_student_documents", ["tenant_id", "generated_document_id"], ["tenant_id", "id"],
    )
    op.create_check_constraint(
        "ck_mira_service_request_priority", "mira_student_service_requests",
        "priority IN ('low','normal','high','urgent')",
    )
    op.create_index(
        "ix_mira_service_work_queue", "mira_student_service_requests",
        ["tenant_id", "status", "due_at", "created_at"],
    )
    op.create_index(
        "ix_mira_service_assignee_queue", "mira_student_service_requests",
        ["tenant_id", "assigned_membership_id", "status"],
    )
    op.create_table(
        "mira_student_service_comments",
        sa.Column("id", U, primary_key=True), _tenant(),
        sa.Column("request_id", U, nullable=False),
        sa.Column("actor_type", sa.String(12), nullable=False),
        sa.Column("actor_user_id", U),
        sa.Column("visibility", sa.String(12), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        _request_fk("fk_mira_service_comment_request_tenant"),
        sa.CheckConstraint("actor_type IN ('staff','student')", name="ck_mira_service_comment_actor"),
        sa.CheckConstraint("visibility IN ('student','staff')", name="ck_mira_service_comment_visibility"),
        sa.CheckConstraint("actor_type != 'student' OR visibility = 'student'", name="ck_mira_service_student_comment_public"),
        sa.CheckConstraint("length(body) BETWEEN 1 AND 2000", name="ck_mira_service_comment_length"),
    )
    op.create_index("ix_mira_service_comment_request", "mira_student_service_comments", ["tenant_id", "request_id", "created_at"])
    op.create_table(
        "mira_student_service_attachments",
        sa.Column("id", U, primary_key=True), _tenant(),
        sa.Column("request_id", U, nullable=False),
        sa.Column("actor_type", sa.String(12), nullable=False),
        sa.Column("actor_user_id", U),
        sa.Column("visibility", sa.String(12), nullable=False),
        sa.Column("filename", sa.String(160), nullable=False),
        sa.Column("content_type", sa.String(60), nullable=False),
        sa.Column("byte_count", sa.Integer(), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        _request_fk("fk_mira_service_attachment_request_tenant"),
        sa.CheckConstraint("actor_type IN ('staff','student')", name="ck_mira_service_attachment_actor"),
        sa.CheckConstraint("visibility IN ('student','staff')", name="ck_mira_service_attachment_visibility"),
        sa.CheckConstraint("actor_type != 'student' OR visibility = 'student'", name="ck_mira_service_student_attachment_public"),
        sa.CheckConstraint("byte_count BETWEEN 1 AND 262144", name="ck_mira_service_attachment_length"),
    )
    op.create_index("ix_mira_service_attachment_request", "mira_student_service_attachments", ["tenant_id", "request_id", "created_at"])
    op.create_table(
        "mira_student_service_notifications",
        sa.Column("id", U, primary_key=True), _tenant(),
        sa.Column("request_id", U, nullable=False),
        sa.Column("recipient_kind", sa.String(12), nullable=False),
        sa.Column("student_id", U),
        sa.Column("staff_user_id", U, sa.ForeignKey("mira_users.id")),
        sa.Column("event_key", sa.String(50), nullable=False),
        sa.Column("title", sa.String(180), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        _request_fk("fk_mira_service_notification_request_tenant"),
        sa.ForeignKeyConstraint(["tenant_id", "student_id"], ["students.tenant_id", "students.id"], name="fk_mira_service_notification_student_tenant"),
        sa.CheckConstraint(
            "(recipient_kind = 'student' AND student_id IS NOT NULL AND staff_user_id IS NULL) OR "
            "(recipient_kind = 'staff' AND staff_user_id IS NOT NULL AND student_id IS NULL)",
            name="ck_mira_service_notification_recipient",
        ),
    )
    op.create_index(
        "ix_mira_service_notification_recipient", "mira_student_service_notifications",
        ["tenant_id", "recipient_kind", "staff_user_id", "student_id", "read_at"],
    )
    op.create_table(
        "mira_student_document_templates",
        sa.Column("id", U, primary_key=True), _tenant(),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("document_kind", sa.String(50), nullable=False),
        sa.Column("body_template", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by_user_id", U, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "id", name="uq_mira_service_template_tenant_id"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_mira_service_template_tenant_name"),
        sa.CheckConstraint("length(body_template) BETWEEN 10 AND 10000", name="ck_mira_service_template_length"),
    )
    for table in TABLES:
        _rls(table)

    # Comments and evidence are permanent audit records: no in-place rewrites or deletes.
    op.get_bind().exec_driver_sql("""
        CREATE FUNCTION mira_service_evidence_immutable() RETURNS trigger AS $wave5$
        BEGIN
            RAISE EXCEPTION 'academic service evidence is append-only';
        END;
        $wave5$ LANGUAGE plpgsql
    """)
    for table in ("mira_student_service_comments", "mira_student_service_attachments"):
        op.execute(f"""CREATE TRIGGER {table}_immutable
            BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION mira_service_evidence_immutable()""")


def downgrade():
    for table in ("mira_student_service_comments", "mira_student_service_attachments"):
        op.execute(f"DROP TRIGGER IF EXISTS {table}_immutable ON {table}")
    op.execute("DROP FUNCTION IF EXISTS mira_service_evidence_immutable()")
    for table in reversed(TABLES):
        op.drop_table(table)
    op.drop_index("ix_mira_service_assignee_queue", table_name="mira_student_service_requests")
    op.drop_index("ix_mira_service_work_queue", table_name="mira_student_service_requests")
    op.drop_constraint("ck_mira_service_request_priority", "mira_student_service_requests", type_="check")
    op.drop_constraint("fk_mira_service_generated_document_tenant", "mira_student_service_requests", type_="foreignkey")
    op.drop_constraint("fk_mira_service_assignee_membership_tenant", "mira_student_service_requests", type_="foreignkey")
    for column in ("generated_document_id", "completed_at", "priority", "due_at", "assigned_at", "assigned_membership_id"):
        op.drop_column("mira_student_service_requests", column)
    op.drop_constraint("uq_mira_memberships_tenant_id_id", "mira_memberships", type_="unique")
