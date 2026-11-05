"""Native MIRA Education catalog, lessons, attendance, grades and calendar.

Revision ID: 057_native_academic_catalog
Revises: 056_native_academic_portal
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "057_native_academic_catalog"
down_revision = "056_native_academic_portal"
branch_labels = None
depends_on = None

U = postgresql.UUID(as_uuid=False)
TABLES = (
    "mira_academic_programs",
    "mira_academic_subjects",
    "mira_academic_teachers",
    "mira_academic_terms",
    "mira_academic_classes",
    "mira_academic_class_enrollments",
    "mira_academic_lessons",
    "mira_academic_attendance",
    "mira_academic_assessments",
    "mira_academic_grades",
    "mira_academic_calendar_events",
    "mira_academic_catalog_audit",
)


def pk():
    return sa.Column("id", U, primary_key=True)


def tid():
    return sa.Column("tenant_id", U, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)


def uuid(name, nullable=False):
    return sa.Column(name, U, nullable=nullable)


def fk(cols, target, name, ondelete="RESTRICT"):
    return sa.ForeignKeyConstraint(["tenant_id", *cols],
                                   [f"{target}.tenant_id", *(f"{target}.{p}" for p in cols)],
                                   name=name, ondelete=ondelete)


def child_fk(cols, target, target_cols, name, ondelete="CASCADE"):
    return sa.ForeignKeyConstraint(["tenant_id", *cols],
                                   [f"{target}.tenant_id", *(f"{target}.{p}" for p in target_cols)],
                                   name=name, ondelete=ondelete)


def protect(name):
    op.execute(f"ALTER TABLE {name} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {name} FORCE ROW LEVEL SECURITY")
    op.execute(f"""
        CREATE POLICY {name}_tenant_access ON {name}
        USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    """)


def upgrade():
    op.create_table(
        "mira_academic_programs",
        pk(), tid(),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("name", sa.String(180), nullable=False),
        sa.Column("modality", sa.String(48)),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "id", name="uq_mira_program_tenant_id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_mira_program_code"),
    )
    op.create_table(
        "mira_academic_subjects",
        pk(), tid(), uuid("program_id"),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("name", sa.String(180), nullable=False),
        sa.Column("credit_hours", sa.Integer()),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_mira_subject_tenant_id"),
        sa.UniqueConstraint("tenant_id", "program_id", "code", name="uq_mira_subject_program_code"),
        child_fk(["program_id"], "mira_academic_programs", ["id"], "fk_mira_subject_program_tenant"),
    )
    op.create_table(
        "mira_academic_teachers",
        pk(), tid(),
        sa.Column("staff_code", sa.String(60), nullable=False),
        sa.Column("display_name", sa.String(180), nullable=False),
        sa.Column("department", sa.String(120)),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_mira_teacher_tenant_id"),
        sa.UniqueConstraint("tenant_id", "staff_code", name="uq_mira_teacher_staff_code"),
    )
    op.create_table(
        "mira_academic_terms",
        pk(), tid(),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("label", sa.String(100), nullable=False),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="planned"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_mira_term_tenant_id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_mira_term_code"),
        sa.CheckConstraint("ends_on >= starts_on", name="ck_mira_term_dates"),
    )
    op.create_table(
        "mira_academic_classes",
        pk(), tid(), uuid("subject_id"), uuid("term_id"), uuid("teacher_id", nullable=True),
        sa.Column("code", sa.String(60), nullable=False),
        sa.Column("campus", sa.String(120)),
        sa.Column("status", sa.String(20), nullable=False, server_default="planned"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_mira_class_tenant_id"),
        sa.UniqueConstraint("tenant_id", "code", "term_id", name="uq_mira_class_code_term"),
        child_fk(["subject_id"], "mira_academic_subjects", ["id"], "fk_mira_class_subject_tenant"),
        child_fk(["term_id"], "mira_academic_terms", ["id"], "fk_mira_class_term_tenant"),
        child_fk(["teacher_id"], "mira_academic_teachers", ["id"], "fk_mira_class_teacher_tenant"),
    )
    op.create_table(
        "mira_academic_class_enrollments",
        pk(), tid(), uuid("class_id"), uuid("student_id"),
        sa.Column("status", sa.String(20), nullable=False, server_default="enrolled"),
        sa.Column("enrolled_on", sa.Date(), nullable=False),
        sa.UniqueConstraint("tenant_id", "class_id", "student_id", name="uq_mira_class_enrollment"),
        child_fk(["class_id"], "mira_academic_classes", ["id"], "fk_mira_enrollment_class_tenant", "CASCADE"),
        child_fk(["student_id"], "students", ["id"], "fk_mira_enrollment_student_tenant", "CASCADE"),
    )
    op.create_index("ix_mira_enrollment_student", "mira_academic_class_enrollments", ["tenant_id", "student_id"])
    op.create_table(
        "mira_academic_lessons",
        pk(), tid(), uuid("class_id"),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("topic", sa.String(200)),
        sa.Column("room", sa.String(120)),
        sa.Column("publication_status", sa.String(20), nullable=False, server_default="draft"),
        sa.UniqueConstraint("tenant_id", "class_id", "id", name="uq_mira_lesson_tenant_class_id"),
        sa.UniqueConstraint("tenant_id", "class_id", "starts_at", name="uq_mira_lesson_class_start"),
        child_fk(["class_id"], "mira_academic_classes", ["id"], "fk_mira_lesson_class_tenant", "CASCADE"),
        sa.CheckConstraint("ends_at > starts_at", name="ck_mira_lesson_duration"),
    )
    op.create_table(
        "mira_academic_attendance",
        pk(), tid(), uuid("class_id"), uuid("lesson_id"), uuid("student_id"),
        sa.Column("status", sa.String(20), nullable=False, server_default="unrecorded"),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "lesson_id", "student_id", name="uq_mira_attendance_lesson_student"),
        child_fk(["class_id", "lesson_id"], "mira_academic_lessons", ["class_id", "id"],
                 "fk_mira_attendance_lesson_tenant_class", "CASCADE"),
        child_fk(["class_id", "student_id"], "mira_academic_class_enrollments", ["class_id", "student_id"],
                 "fk_mira_attendance_enrollment_tenant_class", "CASCADE"),
        sa.CheckConstraint("status IN ('present','absent','excused','unrecorded')",
                           name="ck_mira_attendance_status"),
    )
    op.create_table(
        "mira_academic_assessments",
        pk(), tid(), uuid("class_id"),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("title", sa.String(180), nullable=False),
        sa.Column("max_score", sa.Numeric(8, 2), nullable=False),
        sa.Column("publication_status", sa.String(20), nullable=False, server_default="draft"),
        sa.UniqueConstraint("tenant_id", "class_id", "id", name="uq_mira_assessment_tenant_class_id"),
        sa.UniqueConstraint("tenant_id", "class_id", "code", name="uq_mira_assessment_code"),
        child_fk(["class_id"], "mira_academic_classes", ["id"], "fk_mira_assessment_class_tenant", "CASCADE"),
        sa.CheckConstraint("max_score > 0", name="ck_mira_assessment_max_score"),
    )
    op.create_table(
        "mira_academic_grades",
        pk(), tid(), uuid("class_id"), uuid("assessment_id"), uuid("student_id"),
        sa.Column("score", sa.Numeric(8, 2), nullable=False),
        sa.Column("publication_status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("graded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "assessment_id", "student_id", name="uq_mira_grade_assessment_student"),
        child_fk(["class_id", "assessment_id"], "mira_academic_assessments", ["class_id", "id"],
                 "fk_mira_grade_assessment_tenant_class", "CASCADE"),
        child_fk(["class_id", "student_id"], "mira_academic_class_enrollments", ["class_id", "student_id"],
                 "fk_mira_grade_enrollment_tenant_class", "CASCADE"),
        sa.CheckConstraint("score >= 0", name="ck_mira_grade_nonnegative"),
    )
    op.create_table(
        "mira_academic_calendar_events",
        pk(), tid(), uuid("term_id"), uuid("class_id", nullable=True),
        sa.Column("scope", sa.String(20), nullable=False),
        sa.Column("title", sa.String(180), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("location", sa.String(120)),
        sa.Column("publication_status", sa.String(20), nullable=False, server_default="draft"),
        child_fk(["term_id"], "mira_academic_terms", ["id"], "fk_mira_calendar_term_tenant", "CASCADE"),
        child_fk(["class_id"], "mira_academic_classes", ["id"], "fk_mira_calendar_class_tenant", "CASCADE"),
        sa.CheckConstraint("ends_at > starts_at", name="ck_mira_calendar_duration"),
        sa.CheckConstraint("(scope = 'institution' AND class_id IS NULL) OR "
                           "(scope = 'class' AND class_id IS NOT NULL)", name="ck_mira_calendar_scope"),
    )
    op.create_index("ix_mira_calendar_tenant_time", "mira_academic_calendar_events", ["tenant_id", "starts_at"])
    op.create_table(
        "mira_academic_catalog_audit",
        pk(), tid(),
        sa.Column("actor_user_id", U, sa.ForeignKey("mira_users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("action", sa.String(60), nullable=False),
        sa.Column("counts", postgresql.JSONB, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_mira_academic_catalog_audit_tenant", "mira_academic_catalog_audit",
                    ["tenant_id", "occurred_at"])
    for name in TABLES:
        protect(name)


def downgrade():
    for name in reversed(TABLES):
        op.execute(f"DROP POLICY IF EXISTS {name}_tenant_access ON {name}")
        op.drop_table(name)
