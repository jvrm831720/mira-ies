from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.models.connector_destination import (
    TenantConnectorDestination,
    TenantConnectorDestinationAudit,
)
from app.models.tenant import Tenant


@pytest.mark.asyncio
async def test_postgres_destination_migration_rls_and_append_only_audit(db_session):
    """Exercise the exact RLS policies and triggers installed by Alembic 040."""
    if os.environ.get("MIRA_TEST_PRESERVE_MIGRATED_SCHEMA", "").lower() != "true":
        pytest.skip("Requires the disposable CI database migrated with Alembic.")

    expected_role = os.environ.get("MIRA_REQUIRE_NON_SUPERUSER_DB_ROLE", "mira_test_runner")
    role = (await db_session.execute(text("""
        SELECT current_user, rolsuper, rolbypassrls
        FROM pg_roles
        WHERE rolname = current_user
    """))).one()
    assert role.current_user == expected_role
    assert role.rolsuper is False
    assert role.rolbypassrls is False

    # Verify the exact objects created by migration 040; the test does not
    # create substitute policies or triggers.
    policies = (await db_session.execute(text("""
        SELECT tablename, policyname, cmd
        FROM pg_policies
        WHERE schemaname = current_schema()
          AND tablename IN (
            'tenant_connector_destinations',
            'tenant_connector_destination_audit'
          )
    """))).all()
    assert {(r.tablename, r.policyname, r.cmd) for r in policies} == {
        ("tenant_connector_destinations", "tenant_connector_destinations_isolation", "ALL"),
        ("tenant_connector_destination_audit", "tenant_connector_destination_audit_isolation", "ALL"),
    }

    trigger_rows = (await db_session.execute(text("""
        SELECT c.relname AS table_name, t.tgname AS trigger_name,
               t.tgenabled::text AS tgenabled, p.proname AS function_name
        FROM pg_trigger t
        JOIN pg_class c ON c.oid = t.tgrelid
        JOIN pg_proc p ON p.oid = t.tgfoid
        WHERE NOT t.tgisinternal
          AND c.relname = 'tenant_connector_destination_audit'
    """))).all()
    assert {(r.table_name, r.trigger_name, r.function_name) for r in trigger_rows} == {
        ("tenant_connector_destination_audit", "tenant_connector_destination_audit_append_only", "reject_connector_destination_audit_mutation"),
        ("tenant_connector_destination_audit", "tenant_connector_destination_audit_no_truncate", "reject_connector_destination_audit_mutation"),
    }
    assert all(r.tgenabled == "O" for r in trigger_rows)

    rls = (await db_session.execute(text("""
        SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity
        FROM pg_class c
        WHERE c.relname IN (
          'tenant_connector_destinations',
          'tenant_connector_destination_audit'
        )
    """))).all()
    assert {(r.relname, r.relrowsecurity, r.relforcerowsecurity) for r in rls} == {
        ("tenant_connector_destinations", True, True),
        ("tenant_connector_destination_audit", True, True),
    }

    tenant_a = Tenant(slug=f"egress-a-{uuid.uuid4().hex[:8]}", name="Egress A", is_active=True)
    tenant_b = Tenant(slug=f"egress-b-{uuid.uuid4().hex[:8]}", name="Egress B", is_active=True)
    db_session.add_all([tenant_a, tenant_b])
    await db_session.commit()
    tenant_a_id, tenant_b_id = tenant_a.id, tenant_b.id

    destination_a_id, destination_b_id = str(uuid.uuid4()), str(uuid.uuid4())
    destination_a_id, destination_b_id = str(uuid.uuid4()), str(uuid.uuid4())
    audit_a_id, audit_b_id = str(uuid.uuid4()), str(uuid.uuid4())

    await db_session.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": tenant_a_id})
    db_session.add(TenantConnectorDestination(
        id=destination_a_id, tenant_id=tenant_a_id, connector_key="canvas",
        hostname="canvas.a.example", scheme="https", port=443,
        is_enabled=True, approval_reason="Approved for tenant A",
    ))
    db_session.add(TenantConnectorDestinationAudit(
        id=audit_a_id, tenant_id=tenant_a_id, destination_id=destination_a_id,
        connector_key="canvas", hostname="canvas.a.example", action="approved",
        reason="Approved for tenant A",
    ))
    await db_session.commit()

    await db_session.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": tenant_b_id})
    db_session.add(TenantConnectorDestination(
        id=destination_b_id, tenant_id=tenant_b_id, connector_key="canvas",
        hostname="canvas.b.example", scheme="https", port=443,
        is_enabled=True, approval_reason="Approved for tenant B",
    ))
    db_session.add(TenantConnectorDestinationAudit(
        id=audit_b_id, tenant_id=tenant_b_id, destination_id=destination_b_id,
        connector_key="canvas", hostname="canvas.b.example", action="approved",
        reason="Approved for tenant B",
    ))
    await db_session.commit()

    await db_session.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": tenant_a_id})
    visible_a = (await db_session.execute(text(
        "SELECT id FROM tenant_connector_destinations ORDER BY id"
    ))).scalars().all()
    assert visible_a == [uuid.UUID(destination_a_id)]
    visible_a_audit = (await db_session.execute(text(
        "SELECT id FROM tenant_connector_destination_audit ORDER BY id"
    ))).scalars().all()
    assert visible_a_audit == [uuid.UUID(audit_a_id)]

    # RLS filters cross-tenant writes and rejects cross-tenant inserts.
    result = await db_session.execute(text(
        "UPDATE tenant_connector_destinations SET is_enabled = false WHERE id = :id"
    ), {"id": destination_b_id})
    assert result.rowcount == 0
    with pytest.raises(DBAPIError):
        await db_session.execute(text("""
            INSERT INTO tenant_connector_destinations
                (id, tenant_id, connector_key, hostname, scheme, port,
                 is_enabled, approval_reason)
            VALUES (:id, :tenant_id, 'canvas', 'forged.b.example',
                    'https', 443, true, 'Cross-tenant approval attempt')
        """), {"id": str(uuid.uuid4()), "tenant_id": tenant_b_id})
    await db_session.rollback()

    await db_session.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": tenant_a_id})
    cross_tenant_audit_update = await db_session.execute(text(
        "UPDATE tenant_connector_destination_audit SET reason = 'tampered' WHERE id = :id"
    ), {"id": audit_b_id})
    assert cross_tenant_audit_update.rowcount == 0

    # A tenant may update its own destination and append a revoke event.
    await db_session.execute(text(
        "UPDATE tenant_connector_destinations SET is_enabled = false WHERE id = :id"
    ), {"id": destination_a_id})
    db_session.add(TenantConnectorDestinationAudit(
        id=str(uuid.uuid4()), tenant_id=tenant_a_id, destination_id=destination_a_id,
        connector_key="canvas", hostname="canvas.a.example", action="revoked",
        reason="Revoked for tenant A",
    ))
    await db_session.commit()

    await db_session.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": tenant_a_id})
    with pytest.raises(DBAPIError, match="append-only"):
        await db_session.execute(text(
            "UPDATE tenant_connector_destination_audit SET reason = 'tampered' WHERE id = :id"
        ), {"id": audit_a_id})
    await db_session.rollback()

    await db_session.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": tenant_a_id})
    with pytest.raises(DBAPIError, match="append-only"):
        await db_session.execute(text(
            "DELETE FROM tenant_connector_destination_audit WHERE id = :id"
        ), {"id": audit_a_id})
    await db_session.rollback()

    await db_session.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": tenant_a_id})
    with pytest.raises(DBAPIError, match="append-only"):
        await db_session.execute(text("TRUNCATE TABLE tenant_connector_destination_audit"))
    await db_session.rollback()

    await db_session.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": tenant_b_id})
    visible_b = (await db_session.execute(text(
        "SELECT id FROM tenant_connector_destinations ORDER BY id"
    ))).scalars().all()
    assert visible_b == [uuid.UUID(destination_b_id)]
