"""Tenant-scoped custom roles, permission grants and append-only audit.
Revision ID: 039_tenant_custom_rbac
Revises: 038_high_risk_confirmation
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "039_tenant_custom_rbac"
down_revision = "038_high_risk_confirmation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mira_tenant_roles",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("base_role", sa.String(24), nullable=False, server_default="viewer"),
        sa.Column("permissions", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("mira_users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "name", name="uq_mira_tenant_roles_tenant_name"),
        sa.CheckConstraint("base_role IN ('viewer','operator','coordinator')", name="ck_mira_tenant_roles_base_role"),
    )
    op.create_index("ix_mira_tenant_roles_tenant_active", "mira_tenant_roles", ["tenant_id", "is_active"])
    op.add_column("mira_users", sa.Column("custom_role_id", postgresql.UUID(as_uuid=False), nullable=True))
    op.create_foreign_key("fk_mira_users_custom_role", "mira_users", "mira_tenant_roles", ["custom_role_id"], ["id"], ondelete="SET NULL")
    op.add_column("mira_org_invites", sa.Column("custom_role_id", postgresql.UUID(as_uuid=False), nullable=True))
    op.create_foreign_key("fk_mira_org_invites_custom_role", "mira_org_invites", "mira_tenant_roles", ["custom_role_id"], ["id"], ondelete="SET NULL")
    op.create_table(
        "mira_tenant_role_audit",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("mira_users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("target_user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("mira_users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("role_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("mira_tenant_roles.id", ondelete="SET NULL"), nullable=True),
        sa.Column("event_type", sa.String(48), nullable=False),
        sa.Column("details", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_mira_tenant_role_audit_tenant_created", "mira_tenant_role_audit", ["tenant_id", "created_at"])
    op.execute("""
        CREATE FUNCTION reject_mira_role_audit_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $rbac$
        BEGIN
            IF pg_trigger_depth() > 1 THEN
                IF TG_OP = 'DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
            END IF;
            RAISE EXCEPTION 'mira_tenant_role_audit is append-only';
        END;
        $rbac$
    """)
    op.execute("""
        CREATE TRIGGER trg_mira_tenant_role_audit_append_only
        BEFORE UPDATE OR DELETE ON mira_tenant_role_audit
        FOR EACH ROW EXECUTE FUNCTION reject_mira_role_audit_mutation()
    """)
    op.execute("""
        CREATE FUNCTION protect_last_tenant_admin() RETURNS trigger
        LANGUAGE plpgsql AS $admin$
        DECLARE remaining_admins integer;
        BEGIN
            IF pg_trigger_depth() > 1 THEN
                IF TG_OP = 'DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
            END IF;
            IF TG_OP = 'DELETE' THEN
                IF OLD.role = 'admin' AND OLD.is_active THEN
                    PERFORM 1 FROM tenants WHERE id = OLD.tenant_id FOR UPDATE;
                    SELECT count(*) INTO remaining_admins FROM mira_users
                    WHERE tenant_id = OLD.tenant_id AND role = 'admin'
                      AND is_active IS TRUE AND id <> OLD.id;
                    IF remaining_admins = 0 THEN
                        RAISE EXCEPTION 'cannot remove the last active tenant administrator';
                    END IF;
                END IF;
                RETURN OLD;
            END IF;
            IF OLD.role = 'admin' AND OLD.is_active
               AND (NEW.role <> 'admin' OR NEW.is_active IS FALSE OR NEW.tenant_id <> OLD.tenant_id) THEN
                PERFORM 1 FROM tenants WHERE id = OLD.tenant_id FOR UPDATE;
                SELECT count(*) INTO remaining_admins FROM mira_users
                WHERE tenant_id = OLD.tenant_id AND role = 'admin'
                  AND is_active IS TRUE AND id <> OLD.id;
                IF remaining_admins = 0 THEN
                    RAISE EXCEPTION 'cannot demote or deactivate the last active tenant administrator';
                END IF;
            END IF;
            RETURN NEW;
        END;
        $admin$
    """)
    op.execute("""
        CREATE TRIGGER trg_mira_users_protect_last_admin
        BEFORE UPDATE OF role, is_active, tenant_id OR DELETE ON mira_users
        FOR EACH ROW EXECUTE FUNCTION protect_last_tenant_admin()
    """)
    for table in ("mira_tenant_roles", "mira_tenant_role_audit"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_tenant_isolation ON {table} "
            "USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid) "
            "WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)"
        )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_mira_users_protect_last_admin ON mira_users")
    op.execute("DROP FUNCTION IF EXISTS protect_last_tenant_admin()")
    op.execute("DROP TRIGGER IF EXISTS trg_mira_tenant_role_audit_append_only ON mira_tenant_role_audit")
    op.execute("DROP FUNCTION IF EXISTS reject_mira_role_audit_mutation()")
    op.drop_constraint("fk_mira_org_invites_custom_role", "mira_org_invites", type_="foreignkey")
    op.drop_column("mira_org_invites", "custom_role_id")
    op.drop_constraint("fk_mira_users_custom_role", "mira_users", type_="foreignkey")
    op.drop_column("mira_users", "custom_role_id")
    for table in ("mira_tenant_role_audit", "mira_tenant_roles"):
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_mira_tenant_role_audit_tenant_created", table_name="mira_tenant_role_audit")
    op.drop_table("mira_tenant_role_audit")
    op.drop_index("ix_mira_tenant_roles_tenant_active", table_name="mira_tenant_roles")
    op.drop_table("mira_tenant_roles")
