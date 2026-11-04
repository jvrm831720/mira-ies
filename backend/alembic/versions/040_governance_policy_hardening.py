"""Harden model-governance policy isolation and immutable evidence.

Revision ID: 040_governance_policy_hardening
Revises: 039_tenant_custom_rbac
"""
from alembic import op

revision = "040_governance_policy_hardening"
down_revision = "039_tenant_custom_rbac"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Human tenant sessions and API-key integrations set app.tenant_id after
    # authentication. Internal MIRA administrators set app.is_mira_admin only
    # after their independent Control Center session has been validated.
    for table in ("tenant_data_use_policies", "institutional_training_authorizations"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")
        op.execute(
            f"""
            CREATE POLICY {table}_tenant_isolation ON {table}
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

    # Training events are tenant-owned source records. MIRA governance reads
    # them only through an authenticated internal-admin context.
    op.execute("ALTER TABLE training_events ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE training_events FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY training_events_tenant_isolation ON training_events
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

    # Contract/policy records and the internal audit stream are historical
    # evidence. Revocation is represented by a newer row, never UPDATE/DELETE.
    op.execute(
        """
        CREATE FUNCTION reject_mira_governance_history_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $governance$
        BEGIN
            IF pg_trigger_depth() > 1 THEN
                IF TG_OP = 'DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
            END IF;
            RAISE EXCEPTION 'MIRA governance history is append-only';
        END;
        $governance$
        """
    )
    for table, trigger in (
        ("tenant_data_use_policies", "trg_tenant_data_use_policies_append_only"),
        ("institutional_training_authorizations", "trg_institutional_training_auth_append_only"),
        ("mira_control_admin_audit", "trg_mira_control_admin_audit_append_only"),
    ):
        op.execute(
            f"CREATE TRIGGER {trigger} BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION reject_mira_governance_history_mutation()"
        )


def downgrade() -> None:
    for table, trigger in (
        ("tenant_data_use_policies", "trg_tenant_data_use_policies_append_only"),
        ("institutional_training_authorizations", "trg_institutional_training_auth_append_only"),
        ("mira_control_admin_audit", "trg_mira_control_admin_audit_append_only"),
    ):
        op.execute(f"DROP TRIGGER IF EXISTS {trigger} ON {table}")
    op.execute("DROP FUNCTION IF EXISTS reject_mira_governance_history_mutation()")

    op.execute("DROP POLICY IF EXISTS training_events_tenant_isolation ON training_events")
    op.execute("ALTER TABLE training_events NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE training_events DISABLE ROW LEVEL SECURITY")

    for table in ("tenant_data_use_policies", "institutional_training_authorizations"):
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {table}_tenant_isolation ON {table}
            USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
            WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
            """
        )
