from __future__ import annotations

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
async def test_postgres_destination_rls_and_append_only_audit(db_session):
    """Exercise real PostgreSQL RLS with FORCE ROW LEVEL SECURITY enabled."""
    tenant_a = Tenant(slug="egress-a", name="Egress A", is_active=True)
    tenant_b = Tenant(slug="egress-b", name="Egress B", is_active=True)
    db_session.add_all([tenant_a, tenant_b])
    await db_session.commit()

    statements = [
        "ALTER TABLE tenant_connector_destinations ENABLE ROW LEVEL SECURITY",
        "ALTER TABLE tenant_connector_destinations FORCE ROW LEVEL SECURITY",
        "DROP POLICY IF EXISTS tenant_connector_destinations_test_isolation ON tenant_connector_destinations",
        """CREATE POLICY tenant_connector_destinations_test_isolation
           ON tenant_connector_destinations
           USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
           WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)""",
        "ALTER TABLE tenant_connector_destination_audit ENABLE ROW LEVEL SECURITY",
        "ALTER TABLE tenant_connector_destination_audit FORCE ROW LEVEL SECURITY",
        "DROP POLICY IF EXISTS tenant_connector_destination_audit_test_isolation ON tenant_connector_destination_audit",
        """CREATE POLICY tenant_connector_destination_audit_test_isolation
           ON tenant_connector_destination_audit
           USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
           WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)""",
        """CREATE OR REPLACE FUNCTION reject_connector_destination_audit_mutation_test()
           RETURNS trigger LANGUAGE plpgsql
           AS 'BEGIN RAISE EXCEPTION ''connector destination audit is append-only''; END;'""",
        "DROP TRIGGER IF EXISTS tenant_connector_destination_audit_append_only_test ON tenant_connector_destination_audit",
        """CREATE TRIGGER tenant_connector_destination_audit_append_only_test
           BEFORE UPDATE OR DELETE ON tenant_connector_destination_audit
           FOR EACH ROW EXECUTE FUNCTION reject_connector_destination_audit_mutation_test()""",
    ]
    for statement in statements:
        await db_session.execute(text(statement))
    await db_session.commit()

    destination_a_id = str(uuid.uuid4())
    destination_b_id = str(uuid.uuid4())
    audit_a_id = str(uuid.uuid4())
    audit_b_id = str(uuid.uuid4())

    try:
        await db_session.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": tenant_a.id})
        db_session.add(TenantConnectorDestination(
            id=destination_a_id, tenant_id=tenant_a.id, connector_key="canvas",
            hostname="canvas.a.example", scheme="https", port=443,
            is_enabled=True, approval_reason="Approved for tenant A",
        ))
        db_session.add(TenantConnectorDestinationAudit(
            id=audit_a_id, tenant_id=tenant_a.id, destination_id=destination_a_id,
            connector_key="canvas", hostname="canvas.a.example", action="approved",
            reason="Approved for tenant A",
        ))
        await db_session.commit()

        await db_session.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": tenant_b.id})
        db_session.add(TenantConnectorDestination(
            id=destination_b_id, tenant_id=tenant_b.id, connector_key="canvas",
            hostname="canvas.b.example", scheme="https", port=443,
            is_enabled=True, approval_reason="Approved for tenant B",
        ))
        db_session.add(TenantConnectorDestinationAudit(
            id=audit_b_id, tenant_id=tenant_b.id, destination_id=destination_b_id,
            connector_key="canvas", hostname="canvas.b.example", action="approved",
            reason="Approved for tenant B",
        ))
        await db_session.commit()

        await db_session.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": tenant_a.id})
        visible_a = (await db_session.execute(text(
            "SELECT id FROM tenant_connector_destinations ORDER BY id"
        ))).scalars().all()
        assert visible_a == [destination_a_id]
        visible_a_audit = (await db_session.execute(text(
            "SELECT id FROM tenant_connector_destination_audit ORDER BY id"
        ))).scalars().all()
        assert visible_a_audit == [audit_a_id]

        # A cross-tenant revoke/update is filtered by RLS and changes no row.
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
            """), {"id": str(uuid.uuid4()), "tenant_id": tenant_b.id})
        await db_session.rollback()
        await db_session.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": tenant_a.id})
        cross_tenant_audit_update = await db_session.execute(text(
            "UPDATE tenant_connector_destination_audit SET reason = 'tampered' WHERE id = :id"
        ), {"id": audit_b_id})
        assert cross_tenant_audit_update.rowcount == 0

        # Tenant A can revoke its own destination and append a revocation event.
        await db_session.execute(text(
            "UPDATE tenant_connector_destinations SET is_enabled = false WHERE id = :id"
        ), {"id": destination_a_id})
        db_session.add(TenantConnectorDestinationAudit(
            id=str(uuid.uuid4()), tenant_id=tenant_a.id, destination_id=destination_a_id,
            connector_key="canvas", hostname="canvas.a.example", action="revoked",
            reason="Revoked for tenant A",
        ))
        await db_session.commit()

        with pytest.raises(DBAPIError, match="append-only"):
            await db_session.execute(text(
                "UPDATE tenant_connector_destination_audit SET reason = 'tampered' WHERE id = :id"
            ), {"id": audit_a_id})
        await db_session.rollback()

        await db_session.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": tenant_a.id})
        with pytest.raises(DBAPIError, match="append-only"):
            await db_session.execute(text(
                "DELETE FROM tenant_connector_destination_audit WHERE id = :id"
            ), {"id": audit_a_id})
        await db_session.rollback()

        await db_session.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": tenant_b.id})
        visible_b = (await db_session.execute(text(
            "SELECT id FROM tenant_connector_destinations ORDER BY id"
        ))).scalars().all()
        assert visible_b == [destination_b_id]
    finally:
        await db_session.rollback()
        await db_session.execute(text(
            "DROP TRIGGER IF EXISTS tenant_connector_destination_audit_append_only_test ON tenant_connector_destination_audit"
        ))
        await db_session.execute(text(
            "DROP FUNCTION IF EXISTS reject_connector_destination_audit_mutation_test()"
        ))
        await db_session.execute(text(
            "DROP POLICY IF EXISTS tenant_connector_destinations_test_isolation ON tenant_connector_destinations"
        ))
        await db_session.execute(text(
            "DROP POLICY IF EXISTS tenant_connector_destination_audit_test_isolation ON tenant_connector_destination_audit"
        ))
        await db_session.execute(text("ALTER TABLE tenant_connector_destinations NO FORCE ROW LEVEL SECURITY"))
        await db_session.execute(text("ALTER TABLE tenant_connector_destinations DISABLE ROW LEVEL SECURITY"))
        await db_session.execute(text("ALTER TABLE tenant_connector_destination_audit NO FORCE ROW LEVEL SECURITY"))
        await db_session.execute(text("ALTER TABLE tenant_connector_destination_audit DISABLE ROW LEVEL SECURITY"))
        await db_session.commit()
