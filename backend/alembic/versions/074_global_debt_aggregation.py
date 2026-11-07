"""Wave 2: consented cross-workspace debt disclosure, not cross-tenant DB access."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "074_global_debt_aggregation"
down_revision = "073_global_student_identity"
branch_labels = None
depends_on = None
U = postgresql.UUID(as_uuid=False)


def upgrade():
    op.create_table(
        "mira_global_debt_grants",
        sa.Column("id", U, primary_key=True),
        sa.Column("account_id", U, sa.ForeignKey("mira_global_student_accounts.id"), nullable=False),
        sa.Column("tenant_id", U, sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("student_id", U, nullable=False),
        sa.Column("state", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("evidence_reference", sa.String(120), nullable=False),
        sa.Column("created_by", U, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("accepted_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("state IN ('pending','accepted','revoked')", name="ck_global_debt_grant_state"),
        sa.UniqueConstraint("tenant_id", "student_id", "account_id", name="uq_global_debt_grant"),
        sa.ForeignKeyConstraint(["tenant_id", "student_id"], ["students.tenant_id", "students.id"],
                                name="fk_global_debt_grant_student_tenant"),
    )
    op.create_index("ix_global_debt_grant_account", "mira_global_debt_grants", ["account_id", "state"])
    op.create_index("ix_global_debt_grant_tenant", "mira_global_debt_grants", ["tenant_id", "student_id"])
    op.create_table(
        "mira_global_debt_snapshots",
        sa.Column("id", U, primary_key=True),
        sa.Column("grant_id", U, sa.ForeignKey("mira_global_debt_grants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", U, sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("observation_id", U, nullable=False),
        sa.Column("label", sa.String(180), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("paid_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True)),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("snapshotted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("grant_id", "observation_id", name="uq_global_debt_snapshot"),
        sa.CheckConstraint("amount >= 0 AND paid_amount >= 0 AND paid_amount <= amount",
                           name="ck_global_debt_snapshot_amounts"),
    )
    op.create_index("ix_global_debt_snapshot_grant", "mira_global_debt_snapshots", ["grant_id"])
    for table in ("mira_global_debt_grants", "mira_global_debt_snapshots"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"REVOKE ALL ON TABLE {table} FROM PUBLIC")
        # Tenant staff and global auth each have explicit, disjoint transaction contexts.
        op.execute(f"""CREATE POLICY {table}_scoped ON {table}
          USING (
            (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
            OR current_setting('app.global_identity_service', true) = 'enabled'
          )
          WITH CHECK (
            (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
            OR current_setting('app.global_identity_service', true) = 'enabled'
          )""")


def downgrade():
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM mira_global_debt_grants LIMIT 1) THEN
          RAISE EXCEPTION 'Existing debt grants require reviewed migration';
        END IF;
    END $$""")
    op.drop_table("mira_global_debt_snapshots")
    op.drop_table("mira_global_debt_grants")
