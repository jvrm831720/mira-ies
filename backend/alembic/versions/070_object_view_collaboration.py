"""Wave 3: additive shared views, immutable revisions and user favorites.

Revision ID: 070_object_view_collaboration
Revises: 069_onboarding_logo

Existing personal views remain personal, at revision 1. No student,
collection, campaign or other business records are copied or migrated.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "070_object_view_collaboration"
down_revision = "069_onboarding_logo"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=False)
JSONB = postgresql.JSONB


def upgrade():
    op.add_column("mira_object_views", sa.Column(
        "scope", sa.String(16), nullable=False, server_default="personal",
    ))
    op.add_column("mira_object_views", sa.Column(
        "revision", sa.Integer(), nullable=False, server_default="1",
    ))
    op.add_column("mira_object_views", sa.Column(
        "is_sensitive", sa.Boolean(), nullable=False, server_default=sa.false(),
    ))
    op.create_check_constraint(
        "ck_mira_object_views_scope", "mira_object_views",
        "scope IN ('personal', 'workspace')",
    )
    op.create_check_constraint("ck_mira_object_views_revision", "mira_object_views", "revision >= 1")
    op.create_index("ix_mira_object_views_shared", "mira_object_views",
                    ["tenant_id", "object_key", "scope"])

    # Legacy configs stay at schema_version 1. Conservative sensitivity
    # backfill for old private views; access rules never loosen because of it.
    op.execute("""
        UPDATE mira_object_views SET is_sensitive = true
        WHERE object_key = 'students'
        AND config::text ~ '"(risk_level|risk_score|follow_up)"'
    """)

    # Older checked object keys excluded collections even though the API
    # already supported that object. Add without deleting existing views.
    op.drop_constraint("ck_mira_object_views_object", "mira_object_views", type_="check")
    op.create_check_constraint(
        "ck_mira_object_views_object", "mira_object_views",
        "object_key IN ('students','campaigns','academic_classes',"
        "'academic_programs','academic_subjects','academic_teachers',"
        "'academic_terms','collections')",
    )

    op.create_table(
        "mira_object_view_revisions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("view_id", UUID, nullable=False),
        sa.Column("edited_by_user_id", UUID, sa.ForeignKey("mira_users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("scope", sa.String(16), nullable=False),
        sa.Column("config_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("config", JSONB, nullable=False),
        sa.Column("is_sensitive", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["tenant_id", "view_id"],
                                ["mira_object_views.tenant_id", "mira_object_views.id"],
                                ondelete="CASCADE"),
        sa.UniqueConstraint("view_id", "revision", name="uq_mira_object_view_revision"),
        sa.CheckConstraint("revision >= 1", name="ck_mira_object_view_revision_positive"),
    )
    op.create_index("ix_mira_object_view_revisions_tenant", "mira_object_view_revisions",
                    ["tenant_id", "view_id", "revision"])

    op.create_table(
        "mira_object_view_favorites",
        sa.Column("tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", UUID, sa.ForeignKey("mira_users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("view_id", UUID, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["tenant_id", "view_id"],
                                ["mira_object_views.tenant_id", "mira_object_views.id"],
                                ondelete="CASCADE"),
    )
    op.create_index("ix_mira_view_favorites_user", "mira_object_view_favorites",
                    ["tenant_id", "user_id"])

    # Backfill immutable revision #1 of all existing rows.
    op.execute("""
        INSERT INTO mira_object_view_revisions
        (id, tenant_id, view_id, edited_by_user_id, revision, name, scope,
         config_version, config, is_sensitive, created_at)
        SELECT gen_random_uuid(), tenant_id, id, owner_user_id, 1,
               name, scope, config_version, config, is_sensitive, created_at
        FROM mira_object_views
    """)

    op.execute("DROP POLICY IF EXISTS mira_object_views_owner_policy ON mira_object_views")
    op.execute("""
        CREATE POLICY mira_object_views_read ON mira_object_views FOR SELECT
        USING (
            tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
            AND NULLIF(current_setting('app.user_id', true), '')::uuid IS NOT NULL
            AND (
                owner_user_id = NULLIF(current_setting('app.user_id', true), '')::uuid
                OR (scope = 'workspace' AND
                    (NOT is_sensitive OR current_setting('app.view_sensitive', true) = '1'))
            )
        )
    """)
    op.execute("""
        CREATE POLICY mira_object_views_insert ON mira_object_views FOR INSERT
        WITH CHECK (
            tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
            AND owner_user_id = NULLIF(current_setting('app.user_id', true), '')::uuid
        )
    """)
    op.execute("""
        CREATE POLICY mira_object_views_update ON mira_object_views FOR UPDATE
        USING (
            tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
            AND owner_user_id = NULLIF(current_setting('app.user_id', true), '')::uuid
        )
        WITH CHECK (
            tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
            AND owner_user_id = NULLIF(current_setting('app.user_id', true), '')::uuid
        )
    """)
    op.execute("""
        CREATE POLICY mira_object_views_delete ON mira_object_views FOR DELETE
        USING (
            tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
            AND owner_user_id = NULLIF(current_setting('app.user_id', true), '')::uuid
        )
    """)

    for table in ("mira_object_view_revisions", "mira_object_view_favorites"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"REVOKE ALL ON TABLE {table} FROM PUBLIC")
        op.execute(f"""
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
                    REVOKE ALL ON TABLE {table} FROM anon;
                END IF;
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
                    REVOKE ALL ON TABLE {table} FROM authenticated;
                END IF;
            END;
            $$
        """)

    # Revision history: readable by owner, append-only. No UPDATE or DELETE policy.
    # Cascade on view deletion is the only history removal route.
    op.execute("""
        CREATE POLICY mira_view_revisions_select ON mira_object_view_revisions FOR SELECT
        USING (
            tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
            AND EXISTS (
                SELECT 1 FROM mira_object_views v WHERE
                    v.id = view_id AND v.tenant_id = mira_object_view_revisions.tenant_id
                    AND v.owner_user_id = NULLIF(current_setting('app.user_id', true), '')::uuid
            )
        )
    """)
    op.execute("""
        CREATE POLICY mira_view_revisions_insert ON mira_object_view_revisions FOR INSERT
        WITH CHECK (
            tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
            AND edited_by_user_id = NULLIF(current_setting('app.user_id', true), '')::uuid
            AND EXISTS (
                SELECT 1 FROM mira_object_views v WHERE
                    v.id = view_id AND v.tenant_id = mira_object_view_revisions.tenant_id
                    AND v.owner_user_id = NULLIF(current_setting('app.user_id', true), '')::uuid
            )
        )
    """)
    for operation, predicate in (
        ("SELECT", "USING"),
        ("DELETE", "USING"),
        ("INSERT", "WITH CHECK"),
    ):
        op.execute(f"""
            CREATE POLICY mira_view_favorites_{operation.lower()}
            ON mira_object_view_favorites FOR {operation}
            {predicate} (
                tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
                AND user_id = NULLIF(current_setting('app.user_id', true), '')::uuid
            )
        """)

    # Existing views retain the legacy table grants. New tables are accessed
    # only through FastAPI's server-side DB connection with session GUCs.


def downgrade():
    # Fail closed for workspace sharing; no silent dropping of collaboration.
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM mira_object_views WHERE scope = 'workspace')
               OR EXISTS (SELECT 1 FROM mira_object_view_favorites)
               OR EXISTS (SELECT 1 FROM mira_object_views WHERE revision > 1)
            THEN RAISE EXCEPTION 'Wave 3 collaboration data exists; export before rollback';
            END IF;
        END; $$
    """)
    op.drop_table("mira_object_view_favorites")
    op.drop_table("mira_object_view_revisions")
    for name in ("mira_object_views_read", "mira_object_views_insert",
                 "mira_object_views_update", "mira_object_views_delete"):
        op.execute(f"DROP POLICY IF EXISTS {name} ON mira_object_views")
    op.execute("""
        CREATE POLICY mira_object_views_owner_policy ON mira_object_views
        USING (
            tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
            AND owner_user_id = NULLIF(current_setting('app.user_id', true), '')::uuid
        )
        WITH CHECK (
            tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
            AND owner_user_id = NULLIF(current_setting('app.user_id', true), '')::uuid
        )
    """)
    op.drop_index("ix_mira_object_views_shared", table_name="mira_object_views")
    op.drop_constraint("ck_mira_object_views_revision", "mira_object_views", type_="check")
    op.drop_constraint("ck_mira_object_views_scope", "mira_object_views", type_="check")
    for column in ("is_sensitive", "revision", "scope"):
        op.drop_column("mira_object_views", column)
    op.drop_constraint("ck_mira_object_views_object", "mira_object_views", type_="check")
    op.create_check_constraint(
        "ck_mira_object_views_object", "mira_object_views",
        "object_key IN ('students','campaigns','academic_classes',"
        "'academic_programs','academic_subjects','academic_teachers','academic_terms')",
    )
