"""Versioned academic policies, curricula, admissions and immutable outcomes.

Revision ID: 065_academic_operations
Revises: 064_academic_services_central
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "065_academic_operations"
down_revision = "064_academic_services_central"
branch_labels = None
depends_on = None

U = postgresql.UUID(as_uuid=False)
J = postgresql.JSONB
TABLES = (
    "mira_academic_policies",
    "mira_academic_curricula",
    "mira_academic_curriculum_items",
    "mira_academic_student_programs",
    "mira_academic_enrollment_requests",
    "mira_academic_enrollment_request_classes",
    "mira_academic_class_outcomes",
    "mira_academic_operation_events",
)


def tenant():
    return sa.Column("tenant_id", U, sa.ForeignKey("tenants.id"), nullable=False)


def id_column():
    return sa.Column("id", U, primary_key=True)


def fk(field, table, name):
    return sa.ForeignKeyConstraint(
        ["tenant_id", field], [table + ".tenant_id", table + ".id"], name=name,
    )


def protect(table):
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(f"""CREATE POLICY {table}_tenant_access ON {table}
        USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)""")


def upgrade():
    op.add_column("mira_academic_classes", sa.Column("capacity", sa.Integer()))
    op.add_column("mira_academic_classes", sa.Column("enrollment_open", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("mira_academic_classes", sa.Column("policy_version", sa.Integer()))
    op.create_check_constraint("ck_mira_academic_class_capacity", "mira_academic_classes",
                               "capacity IS NULL OR capacity BETWEEN 1 AND 10000")
    op.create_table(
        "mira_academic_policies",
        id_column(), tenant(), sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("passing_percent", sa.Numeric(5, 2), nullable=False),
        sa.Column("min_attendance_percent", sa.Numeric(5, 2), nullable=False),
        sa.Column("max_classes_per_term", sa.Integer(), nullable=False),
        sa.Column("excused_excluded", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("allow_reenrollment", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("enrollment_opens_on", sa.Date()),
        sa.Column("enrollment_closes_on", sa.Date()),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("created_by_user_id", U, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("tenant_id", "id", name="uq_mira_academic_policy_tenant_id"),
        sa.UniqueConstraint("tenant_id", "version", name="uq_mira_academic_policy_version"),
        sa.CheckConstraint("status IN ('draft','published')", name="ck_mira_academic_policy_status"),
        sa.CheckConstraint("passing_percent BETWEEN 0 AND 100", name="ck_mira_academic_policy_grade"),
        sa.CheckConstraint("min_attendance_percent BETWEEN 0 AND 100", name="ck_mira_academic_policy_attendance"),
        sa.CheckConstraint("max_classes_per_term BETWEEN 1 AND 30", name="ck_mira_academic_policy_class_limit"),
        sa.CheckConstraint("enrollment_closes_on IS NULL OR enrollment_opens_on IS NULL OR enrollment_closes_on >= enrollment_opens_on", name="ck_mira_academic_policy_window"),
    )
    op.create_foreign_key(
        "fk_mira_class_policy_version_tenant", "mira_academic_classes",
        "mira_academic_policies", ["tenant_id", "policy_version"], ["tenant_id", "version"],
    )
    op.create_table(
        "mira_academic_curricula",
        id_column(), tenant(), sa.Column("program_id", U, nullable=False),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("label", sa.String(160), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("created_by_user_id", U, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("tenant_id", "id", name="uq_mira_academic_curriculum_tenant_id"),
        sa.UniqueConstraint("tenant_id", "program_id", "code", name="uq_mira_academic_curriculum_code"),
        sa.CheckConstraint("status IN ('draft','published')", name="ck_mira_academic_curriculum_status"),
        fk("program_id", "mira_academic_programs", "fk_mira_curriculum_program_tenant"),
    )
    op.create_table(
        "mira_academic_curriculum_items",
        id_column(), tenant(), sa.Column("curriculum_id", U, nullable=False),
        sa.Column("subject_id", U, nullable=False),
        sa.Column("period_number", sa.Integer(), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("prerequisite_subject_id", U),
        sa.UniqueConstraint("tenant_id", "curriculum_id", "subject_id", name="uq_mira_academic_curriculum_subject"),
        fk("curriculum_id", "mira_academic_curricula", "fk_mira_curriculum_item_curriculum_tenant"),
        fk("subject_id", "mira_academic_subjects", "fk_mira_curriculum_item_subject_tenant"),
        fk("prerequisite_subject_id", "mira_academic_subjects", "fk_mira_curriculum_item_prereq_tenant"),
        sa.CheckConstraint("period_number BETWEEN 1 AND 30", name="ck_mira_curriculum_period"),
        sa.CheckConstraint("prerequisite_subject_id IS NULL OR prerequisite_subject_id != subject_id", name="ck_mira_curriculum_not_self_prereq"),
    )
    op.create_table(
        "mira_academic_student_programs",
        id_column(), tenant(),
        sa.Column("student_id", U, nullable=False),
        sa.Column("program_id", U, nullable=False),
        sa.Column("curriculum_id", U, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("admitted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "id", name="uq_mira_student_program_tenant_id"),
        sa.UniqueConstraint("tenant_id", "student_id", "program_id", name="uq_mira_student_program"),
        fk("student_id", "students", "fk_mira_student_program_student_tenant"),
        fk("program_id", "mira_academic_programs", "fk_mira_student_program_program_tenant"),
        fk("curriculum_id", "mira_academic_curricula", "fk_mira_student_program_curriculum_tenant"),
        sa.CheckConstraint("status IN ('active','suspended','completed','cancelled')", name="ck_mira_student_program_status"),
    )
    op.create_index("ix_mira_student_program_student", "mira_academic_student_programs", ["tenant_id", "student_id"])
    op.create_table(
        "mira_academic_enrollment_requests",
        id_column(), tenant(),
        sa.Column("student_program_id", U, nullable=False),
        sa.Column("term_id", U, nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="submitted"),
        sa.Column("requested_by", sa.String(12), nullable=False),
        sa.Column("requested_by_user_id", U),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("decided_by_user_id", U),
        sa.Column("decision_note", sa.String(500)),
        sa.Column("policy_snapshot", J, nullable=False),
        sa.UniqueConstraint("tenant_id", "id", name="uq_mira_enrollment_request_tenant_id"),
        sa.UniqueConstraint("tenant_id", "student_program_id", "term_id", name="uq_mira_enrollment_request_student_term"),
        fk("student_program_id", "mira_academic_student_programs", "fk_mira_enrollment_request_program_tenant"),
        fk("term_id", "mira_academic_terms", "fk_mira_enrollment_request_term_tenant"),
        sa.CheckConstraint("kind IN ('enrollment','reenrollment')", name="ck_mira_enrollment_request_kind"),
        sa.CheckConstraint("status IN ('submitted','approved','rejected')", name="ck_mira_enrollment_request_status"),
    )
    op.create_index("ix_mira_enrollment_requests_queue", "mira_academic_enrollment_requests", ["tenant_id", "status", "submitted_at"])
    op.create_table(
        "mira_academic_enrollment_request_classes",
        id_column(), tenant(),
        sa.Column("request_id", U, nullable=False), sa.Column("class_id", U, nullable=False),
        sa.UniqueConstraint("tenant_id", "request_id", "class_id", name="uq_mira_enrollment_request_class"),
        fk("request_id", "mira_academic_enrollment_requests", "fk_mira_enrollment_req_class_request_tenant"),
        fk("class_id", "mira_academic_classes", "fk_mira_enrollment_req_class_class_tenant"),
    )
    op.create_table(
        "mira_academic_class_outcomes",
        id_column(), tenant(),
        sa.Column("class_id", U, nullable=False),
        sa.Column("student_id", U, nullable=False),
        sa.Column("score_percent", sa.Numeric(5, 2), nullable=False),
        sa.Column("attendance_percent", sa.Numeric(5, 2), nullable=False),
        sa.Column("result", sa.String(12), nullable=False),
        sa.Column("policy_snapshot", J, nullable=False),
        sa.Column("closed_by_user_id", U, nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "class_id", "student_id", name="uq_mira_academic_class_outcome_student"),
        fk("class_id", "mira_academic_classes", "fk_mira_outcome_class_tenant"),
        fk("student_id", "students", "fk_mira_outcome_student_tenant"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "class_id", "student_id"],
            ["mira_academic_class_enrollments.tenant_id",
             "mira_academic_class_enrollments.class_id",
             "mira_academic_class_enrollments.student_id"],
            name="fk_mira_outcome_class_enrollment_tenant",
        ),
        sa.CheckConstraint("result IN ('passed','failed')", name="ck_mira_outcome_result"),
        sa.CheckConstraint("score_percent BETWEEN 0 AND 100", name="ck_mira_outcome_score"),
        sa.CheckConstraint("attendance_percent BETWEEN 0 AND 100", name="ck_mira_outcome_attendance"),
    )
    op.create_index("ix_mira_academic_outcome_student", "mira_academic_class_outcomes", ["tenant_id", "student_id", "closed_at"])
    op.create_table(
        "mira_academic_operation_events",
        id_column(), tenant(),
        sa.Column("actor_kind", sa.String(12), nullable=False),
        sa.Column("actor_user_id", U),
        sa.Column("event_type", sa.String(60), nullable=False),
        sa.Column("target_kind", sa.String(40), nullable=False),
        sa.Column("target_id", U, nullable=False),
        sa.Column("details", J, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_mira_academic_op_events", "mira_academic_operation_events",
                    ["tenant_id", "target_kind", "target_id", "occurred_at"])

    for table in TABLES:
        protect(table)

    op.get_bind().exec_driver_sql("""
        CREATE FUNCTION mira_academic_wave6_guard() RETURNS trigger AS $w6$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'published academic record or audit cannot be deleted';
            END IF;
            IF TG_TABLE_NAME IN ('mira_academic_class_outcomes','mira_academic_operation_events') THEN
                RAISE EXCEPTION 'academic result and operation audit are immutable';
            END IF;
            IF OLD.status = 'published' THEN
                RAISE EXCEPTION 'published academic rule/curriculum is immutable';
            END IF;
            RETURN NEW;
        END;
        $w6$ LANGUAGE plpgsql
    """)
    for table in ("mira_academic_policies", "mira_academic_curricula",
                  "mira_academic_class_outcomes", "mira_academic_operation_events"):
        op.execute(f"""CREATE TRIGGER {table}_guard BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION mira_academic_wave6_guard()""")
    op.get_bind().exec_driver_sql("""
        CREATE FUNCTION mira_academic_curriculum_item_guard() RETURNS trigger AS $w6item$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                IF EXISTS (SELECT 1 FROM mira_academic_curricula
                           WHERE tenant_id = NEW.tenant_id
                             AND id = NEW.curriculum_id AND status = 'published') THEN
                    RAISE EXCEPTION 'cannot append to a published curriculum';
                END IF;
                RETURN NEW;
            END IF;
            IF EXISTS (SELECT 1 FROM mira_academic_curricula WHERE tenant_id = OLD.tenant_id
                       AND id = OLD.curriculum_id AND status = 'published') THEN
                RAISE EXCEPTION 'cannot change a published curriculum';
            END IF;
            IF TG_OP = 'UPDATE' AND EXISTS (
                SELECT 1 FROM mira_academic_curricula
                WHERE tenant_id = NEW.tenant_id
                  AND id = NEW.curriculum_id AND status = 'published'
            ) THEN
                RAISE EXCEPTION 'cannot move an item to a published curriculum';
            END IF;
            IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
            RETURN NEW;
        END;
        $w6item$ LANGUAGE plpgsql
    """)
    op.execute("""CREATE TRIGGER mira_academic_curriculum_item_guard
        BEFORE INSERT OR UPDATE OR DELETE ON mira_academic_curriculum_items
        FOR EACH ROW EXECUTE FUNCTION mira_academic_curriculum_item_guard()""")


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS mira_academic_curriculum_item_guard ON mira_academic_curriculum_items")
    op.execute("DROP FUNCTION IF EXISTS mira_academic_curriculum_item_guard()")
    for table in ("mira_academic_policies", "mira_academic_curricula",
                  "mira_academic_class_outcomes", "mira_academic_operation_events"):
        op.execute(f"DROP TRIGGER IF EXISTS {table}_guard ON {table}")
    op.execute("DROP FUNCTION IF EXISTS mira_academic_wave6_guard()")
    op.drop_constraint("fk_mira_class_policy_version_tenant", "mira_academic_classes", type_="foreignkey")
    for table in reversed(TABLES):
        op.drop_table(table)
    op.drop_constraint("ck_mira_academic_class_capacity", "mira_academic_classes", type_="check")
    op.drop_column("mira_academic_classes", "enrollment_open")
    op.drop_column("mira_academic_classes", "policy_version")
    op.drop_column("mira_academic_classes", "capacity")
