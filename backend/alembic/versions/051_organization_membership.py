"""Phase B: Organization, Membership, branding and module entitlements.

Additive only. User.tenant_id and User.role remain the live path.
Backfill creates 1:1 Organization + active Membership for every existing user.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "051_organization_membership"
down_revision: Union[str, None] = "050_omie_finance_connection"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Organization ──────────────────────────────────────────────
    op.create_table(
        "mira_organizations",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("legal_name", sa.String(255), nullable=False),
        sa.Column("trade_name", sa.String(255), nullable=True),
        sa.Column("country_code", sa.String(2), nullable=False, server_default="BR"),
        sa.Column("tax_id_normalized", sa.String(32), nullable=True),
        sa.Column("tax_id_display", sa.String(32), nullable=True),
        sa.Column("operation_profile", sa.String(32), nullable=False, server_default="institution"),
        sa.Column("tax_id_source", sa.String(64), nullable=True),
        sa.Column("tax_id_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("address_snapshot", postgresql.JSONB(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("country_code", "tax_id_normalized", name="uq_mira_organizations_tax_id"),
    )
    op.create_index("ix_mira_organizations_tax_id", "mira_organizations", ["tax_id_normalized"])
    op.create_index("ix_mira_organizations_created", "mira_organizations", ["created_at"])

    # Link tenant → organization (nullable during transition)
    op.add_column(
        "tenants",
        sa.Column("organization_id", postgresql.UUID(as_uuid=False), nullable=True),
    )
    op.create_foreign_key(
        "fk_tenants_organization_id",
        "tenants",
        "mira_organizations",
        ["organization_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_tenants_organization_id", "tenants", ["organization_id"])

    # ── Membership ────────────────────────────────────────────────
    op.create_table(
        "mira_memberships",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("role", sa.String(32), nullable=False, server_default="coordinator"),
        sa.Column("custom_role_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("origin", sa.String(32), nullable=False, server_default="legacy_backfill"),
        sa.Column("invited_by_user_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("left_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["mira_users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["invited_by_user_id"], ["mira_users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "custom_role_id"],
            ["mira_tenant_roles.tenant_id", "mira_tenant_roles.id"],
            name="fk_mira_memberships_custom_role_tenant",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'invited', 'suspended', 'left')",
            name="ck_mira_memberships_status",
        ),
        sa.UniqueConstraint("user_id", "tenant_id", name="uq_mira_memberships_user_tenant"),
    )
    op.create_index("ix_mira_memberships_user", "mira_memberships", ["user_id"])
    op.create_index("ix_mira_memberships_tenant_status", "mira_memberships", ["tenant_id", "status"])

    # ── Branding & domains ────────────────────────────────────────
    op.create_table(
        "mira_tenant_branding",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("logo_storage_key", sa.String(500), nullable=True),
        sa.Column("primary_color", sa.String(16), nullable=True),
        sa.Column("support_email", sa.String(255), nullable=True),
        sa.Column("support_url", sa.String(500), nullable=True),
        sa.Column("portal_title", sa.String(120), nullable=True),
        sa.Column("extra", postgresql.JSONB(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "mira_tenant_domains",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("hostname", sa.String(255), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("verification_token", sa.String(128), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("hostname", name="uq_mira_tenant_domains_hostname"),
    )
    op.create_index("ix_mira_tenant_domains_tenant", "mira_tenant_domains", ["tenant_id"])

    # ── Module entitlements ───────────────────────────────────────
    op.create_table(
        "mira_module_entitlements",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("module_key", sa.String(48), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="enabled"),
        sa.Column("source", sa.String(32), nullable=False, server_default="default"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("tenant_id", "module_key", name="uq_mira_module_entitlements_tenant_module"),
    )
    op.create_index("ix_mira_module_entitlements_tenant", "mira_module_entitlements", ["tenant_id"])

    # ── Backfill: one deterministic Organization for each existing Tenant ──
    # Keep both generated IDs in a transaction-local mapping; never infer
    # ownership by joining on a name or timestamp (which may collide).
    op.execute(
        """
        CREATE TEMP TABLE _mira_tenant_organization_map ON COMMIT DROP AS
        SELECT
            t.id AS tenant_id,
            gen_random_uuid() AS organization_id,
            t.name AS legal_name,
            COALESCE(t.is_active, true) AS is_active,
            COALESCE(t.created_at, now()) AS created_at
        FROM tenants t
        WHERE t.organization_id IS NULL
        """
    )
    op.execute(
        """
        INSERT INTO mira_organizations (
            id, legal_name, trade_name, country_code, operation_profile,
            is_active, created_at, updated_at
        )
        SELECT organization_id, legal_name, legal_name, 'BR', 'institution',
               is_active, created_at, now()
        FROM _mira_tenant_organization_map
        """
    )
    op.execute(
        """
        UPDATE tenants t
        SET organization_id = mapping.organization_id
        FROM _mira_tenant_organization_map mapping
        WHERE t.id = mapping.tenant_id AND t.organization_id IS NULL
        """
    )

    # 2. One active Membership per existing User
    op.execute(
        """
        INSERT INTO mira_memberships (
            id, user_id, tenant_id, role, custom_role_id, status, origin, joined_at, created_at, updated_at
        )
        SELECT
            gen_random_uuid()::text,
            u.id,
            u.tenant_id,
            COALESCE(u.role, 'coordinator'),
            u.custom_role_id,
            CASE WHEN COALESCE(u.is_active, true) THEN 'active' ELSE 'suspended' END,
            'legacy_backfill',
            COALESCE(u.onboarding_completed_at, u.created_at),
            COALESCE(u.created_at, now()),
            now()
        FROM mira_users u
        WHERE NOT EXISTS (
            SELECT 1 FROM mira_memberships m
            WHERE m.user_id = u.id AND m.tenant_id = u.tenant_id
        )
        """
    )

    # 3. Default module entitlements for every tenant (permanence + workspace + data)
    op.execute(
        """
        INSERT INTO mira_module_entitlements (id, tenant_id, module_key, status, source, created_at, updated_at)
        SELECT gen_random_uuid()::text, t.id, mod.key, 'enabled', 'default', now(), now()
        FROM tenants t
        CROSS JOIN (VALUES ('permanence'), ('data'), ('workspace'), ('mira_plan')) AS mod(key)
        WHERE NOT EXISTS (
            SELECT 1 FROM mira_module_entitlements e
            WHERE e.tenant_id = t.id AND e.module_key = mod.key
        )
        """
    )


def downgrade() -> None:
    op.drop_table("mira_module_entitlements")
    op.drop_table("mira_tenant_domains")
    op.drop_table("mira_tenant_branding")
    op.drop_table("mira_memberships")
    op.drop_constraint("fk_tenants_organization_id", "tenants", type_="foreignkey")
    op.drop_index("ix_tenants_organization_id", table_name="tenants")
    op.drop_column("tenants", "organization_id")
    op.drop_table("mira_organizations")
