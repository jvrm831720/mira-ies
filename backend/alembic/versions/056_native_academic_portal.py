"""MIRA-native academic records and student self-service portal (disabled by default).

Revision ID: 056_native_academic_portal
Revises: 055_eligible_contrib_revocation
No Frappe service, MariaDB or Redis is required.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "056_native_academic_portal"
down_revision = "055_eligible_contrib_revocation"
branch_labels = None
depends_on = None

U = postgresql.UUID(as_uuid=False)


def _tenant_isolation(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(f"""
        CREATE POLICY {table}_tenant_access ON {table}
        USING (
            tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        )
        WITH CHECK (
            tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        )
    """)


def upgrade() -> None:
    # Composite FK guarantees that portal records cannot point at another IES.
    # Index precondition must be validated on the target PostgreSQL before rollout.
    op.execute("""
    DO $mira$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'uq_students_tenant_id_id'
              AND conrelid = 'students'::regclass
        ) THEN
            ALTER TABLE students ADD CONSTRAINT uq_students_tenant_id_id
            UNIQUE (tenant_id, id);
        END IF;
    END $mira$;
    """)

    op.create_table(
        "mira_academic_records",
        sa.Column("id", U, primary_key=True),
        sa.Column("tenant_id", U, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("student_id", U, nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("source", sa.String(60), nullable=False),
        sa.Column("source_record_id", sa.String(120), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("academic_period", sa.String(60), nullable=True),
        sa.Column("status", sa.String(60), nullable=True),
        sa.Column("event_date", sa.Date(), nullable=True),
        sa.Column("grade", sa.Numeric(8, 2), nullable=True),
        sa.Column("max_grade", sa.Numeric(8, 2), nullable=True),
        sa.Column("amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("currency", sa.String(3), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id", "student_id"], ["students.tenant_id", "students.id"],
                                name="fk_mira_academic_student_tenant", ondelete="CASCADE"),
        sa.UniqueConstraint("tenant_id", "student_id", "kind", "source", "source_record_id",
                            name="uq_mira_academic_source_record"),
    )
    op.create_index("ix_mira_academic_student_kind", "mira_academic_records",
                    ["tenant_id", "student_id", "kind"])
    _tenant_isolation("mira_academic_records")

    op.create_table(
        "mira_student_portal_invites",
        sa.Column("id", U, primary_key=True),
        sa.Column("tenant_id", U, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("student_id", U, nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("issued_by_user_id", U,
                  sa.ForeignKey("mira_users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id", "student_id"], ["students.tenant_id", "students.id"],
                                name="fk_mira_portal_invite_student_tenant", ondelete="CASCADE"),
    )
    op.create_index("ix_mira_portal_invites_tenant_student", "mira_student_portal_invites",
                    ["tenant_id", "student_id"])
    _tenant_isolation("mira_student_portal_invites")

    op.create_table(
        "mira_student_portal_sessions",
        sa.Column("id", U, primary_key=True),
        sa.Column("tenant_id", U, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("student_id", U, nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id", "student_id"], ["students.tenant_id", "students.id"],
                                name="fk_mira_portal_session_student_tenant", ondelete="CASCADE"),
    )
    op.create_index("ix_mira_portal_sessions_student", "mira_student_portal_sessions",
                    ["tenant_id", "student_id", "revoked_at"])
    _tenant_isolation("mira_student_portal_sessions")


def downgrade() -> None:
    # Destructive rollback of portal data; keep students and their existing uniqueness.
    for table in ("mira_student_portal_sessions", "mira_student_portal_invites", "mira_academic_records"):
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_access ON {table}")
    op.drop_index("ix_mira_portal_sessions_student", table_name="mira_student_portal_sessions")
    op.drop_table("mira_student_portal_sessions")
    op.drop_index("ix_mira_portal_invites_tenant_student", table_name="mira_student_portal_invites")
    op.drop_table("mira_student_portal_invites")
    op.drop_index("ix_mira_academic_student_kind", table_name="mira_academic_records")
    op.drop_table("mira_academic_records")
