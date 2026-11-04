from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models.connector_destination import TenantConnectorDestinationAudit


@pytest.mark.asyncio
async def test_admin_can_approve_list_and_revoke_only_own_tenant_destination(
    client, tenant_factory, db_session
):
    tenant_a, key_a = await tenant_factory("dest-a", "Destination A")
    tenant_b, key_b = await tenant_factory("dest-b", "Destination B")

    approved = await client.post(
        "/api/v1/security/connector-destinations",
        headers={"X-API-Key": key_a},
        json={
            "connector_key": "canvas",
            "hostname": "canvas.tenant-a.example",
            "reason": "Approved endpoint for tenant A",
        },
    )
    assert approved.status_code == 201
    destination_id = approved.json()["id"]

    listed_a = await client.get(
        "/api/v1/security/connector-destinations", headers={"X-API-Key": key_a}
    )
    assert listed_a.status_code == 200
    assert [item["id"] for item in listed_a.json()] == [destination_id]

    listed_b = await client.get(
        "/api/v1/security/connector-destinations", headers={"X-API-Key": key_b}
    )
    assert listed_b.status_code == 200
    assert listed_b.json() == []

    cross_tenant_revoke = await client.delete(
        f"/api/v1/security/connector-destinations/{destination_id}",
        headers={"X-API-Key": key_b},
        params={"reason": "Attempt cross tenant revoke"},
    )
    assert cross_tenant_revoke.status_code == 404

    revoked = await client.delete(
        f"/api/v1/security/connector-destinations/{destination_id}",
        headers={"X-API-Key": key_a},
        params={"reason": "Tenant A revoked endpoint"},
    )
    assert revoked.status_code == 200
    assert revoked.json()["enabled"] is False

    await db_session.refresh(tenant_a)
    await db_session.refresh(tenant_b)
    audit_a = (
        await db_session.execute(
            select(TenantConnectorDestinationAudit).where(
                TenantConnectorDestinationAudit.tenant_id == tenant_a.id
            )
        )
    ).scalars().all()
    assert [event.action for event in audit_a] == ["approved", "revoked"]
    audit_b = (
        await db_session.execute(
            select(TenantConnectorDestinationAudit).where(
                TenantConnectorDestinationAudit.tenant_id == tenant_b.id
            )
        )
    ).scalars().all()
    assert audit_b == []
