"""HTTP contract tests for the TOTVS RM operations API."""
from __future__ import annotations

from uuid import uuid4

import pytest

from app.db.session import AsyncSessionLocal
from app.services.connectors.totvs_rm_sync_orchestrator import RMPostgresSyncQueue


BASE = "/api/v1/integrations/totvs-rm"


@pytest.mark.asyncio
async def test_create_list_detail_cancel_and_metrics(client, tenant, auth_headers):
    response = await client.post(
        f"{BASE}/sync",
        headers={**auth_headers, "Idempotency-Key": f"api-{uuid4()}"},
        json={
            "coligada_id": "001",
            "source_name": "EduAlunoData",
            "entity_name": "students",
            "schema_version": "v1",
            "page_size": 250,
            "max_attempts": 4,
        },
    )
    assert response.status_code == 202, response.text
    created = response.json()
    assert created["status"] == "queued"

    scopes = await client.get(f"{BASE}/scopes", headers=auth_headers)
    assert scopes.status_code == 200
    assert any(scope["id"] == created["scope_id"] for scope in scopes.json()["scopes"])

    listing = await client.get(f"{BASE}/jobs?status=queued", headers=auth_headers)
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert listing.json()["jobs"][0]["id"] == created["job_id"]
    assert listing.json()["jobs"][0]["request"] == {"mode": "full_snapshot", "page_size": 250}

    detail = await client.get(f"{BASE}/jobs/{created['job_id']}", headers=auth_headers)
    assert detail.status_code == 200
    assert detail.json()["events"][0]["event_type"] == "queued"

    cancelled = await client.post(
        f"{BASE}/jobs/{created['job_id']}/cancel", headers=auth_headers
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    repeated_cancel = await client.post(
        f"{BASE}/jobs/{created['job_id']}/cancel", headers=auth_headers
    )
    assert repeated_cancel.status_code == 200
    assert repeated_cancel.json()["status"] == "cancelled"
    detail_after_cancel = await client.get(
        f"{BASE}/jobs/{created['job_id']}", headers=auth_headers
    )
    cancel_events = [
        event for event in detail_after_cancel.json()["events"]
        if event["event_type"] == "cancelled"
    ]
    assert len(cancel_events) == 1
    assert cancel_events[0]["details"]["actor_type"] == "api_key"

    metrics = await client.get(f"{BASE}/metrics", headers=auth_headers)
    assert metrics.status_code == 200
    assert metrics.json()["jobs_by_status"]["cancelled"] == 1


@pytest.mark.asyncio
async def test_idempotency_and_validation_contract(client, tenant, auth_headers):
    key = f"same-{uuid4()}"
    body = {
        "coligada_id": "002",
        "source_name": "EduParcelaData",
        "entity_name": "installments",
    }
    first = await client.post(
        f"{BASE}/sync", headers={**auth_headers, "Idempotency-Key": key}, json=body
    )
    second = await client.post(
        f"{BASE}/sync", headers={**auth_headers, "Idempotency-Key": key}, json=body
    )
    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["job_id"] == second.json()["job_id"]

    invalid = await client.post(
        f"{BASE}/sync",
        headers={**auth_headers, "Idempotency-Key": f"invalid-{uuid4()}"},
        json={**body, "coligada_id": "../another-tenant"},
    )
    assert invalid.status_code == 422

    conflict = await client.post(
        f"{BASE}/sync",
        headers={**auth_headers, "Idempotency-Key": key},
        json={**body, "page_size": 100},
    )
    assert conflict.status_code == 409

    retry_policy_conflict = await client.post(
        f"{BASE}/sync",
        headers={**auth_headers, "Idempotency-Key": key},
        json={**body, "max_attempts": 4},
    )
    assert retry_policy_conflict.status_code == 409


@pytest.mark.asyncio
async def test_retry_failed_job_is_audited_and_limited_to_failed_jobs(
    client, tenant, auth_headers
):
    tenant_row, _ = tenant
    queue = RMPostgresSyncQueue(AsyncSessionLocal)
    scope_id = await queue.ensure_scope(
        tenant_id=str(tenant_row.id), coligada_id="003",
        source_name="EduParcelaData", entity_name="installments", schema_version="v1",
    )
    job_id = await queue.enqueue(
        tenant_id=str(tenant_row.id), scope_id=scope_id,
        idempotency_key=f"retry-{uuid4()}", request={"mode": "full_snapshot"},
    )
    claimed = await queue.claim(tenant_id=str(tenant_row.id), worker_id="api-test-worker")
    assert claimed and claimed["id"] == job_id
    await queue.fail(
        tenant_id=str(tenant_row.id), job_id=job_id, worker_id="api-test-worker",
        exc=ValueError("invalid mapping"), attempt=claimed["attempt"],
        max_attempts=claimed["max_attempts"],
    )

    retried = await client.post(f"{BASE}/jobs/{job_id}/retry", headers=auth_headers)
    assert retried.status_code == 202, retried.text
    assert retried.json()["status"] == "queued"
    assert retried.json()["manual_retry_number"] == 1

    events = await client.get(f"{BASE}/jobs/{job_id}", headers=auth_headers)
    assert events.status_code == 200
    retry_events = [
        event for event in events.json()["events"]
        if event["event_type"] == "manual_retry"
    ]
    assert len(retry_events) == 1
    assert retry_events[0]["details"]["actor_type"] == "api_key"

    second_retry = await client.post(f"{BASE}/jobs/{job_id}/retry", headers=auth_headers)
    assert second_retry.status_code == 409


@pytest.mark.asyncio
async def test_job_detail_is_not_visible_to_another_tenant(
    client, tenant, tenant_factory, auth_headers
):
    tenant_row, _ = tenant
    _, other_key = await tenant_factory(slug="other-ies")
    queue = RMPostgresSyncQueue(AsyncSessionLocal)
    scope_id = await queue.ensure_scope(
        tenant_id=str(tenant_row.id), coligada_id="004",
        source_name="EduAlunoData", entity_name="students", schema_version="v1",
    )
    job_id = await queue.enqueue(
        tenant_id=str(tenant_row.id), scope_id=scope_id,
        idempotency_key=f"tenant-{uuid4()}", request={"mode": "full_snapshot"},
    )
    response = await client.get(
        f"{BASE}/jobs/{job_id}",
        headers={"X-API-Key": other_key},
    )
    assert response.status_code == 404

    malformed_id = await client.get(f"{BASE}/jobs/not-a-uuid", headers=auth_headers)
    assert malformed_id.status_code == 422

    missing_id = str(uuid4())
    missing_cancel = await client.post(
        f"{BASE}/jobs/{missing_id}/cancel", headers=auth_headers
    )
    missing_retry = await client.post(
        f"{BASE}/jobs/{missing_id}/retry", headers=auth_headers
    )
    assert missing_cancel.status_code == 404
    assert missing_retry.status_code == 404


@pytest.mark.asyncio
async def test_operations_require_coordinator_or_higher(client, tenant):
    from app.core.auth import AuthContext, get_current_tenant
    from app.main import app

    tenant_row, _ = tenant
    app.dependency_overrides[get_current_tenant] = lambda: AuthContext(
        tenant=tenant_row, tenant_id=str(tenant_row.id),
        tenant_slug=tenant_row.slug, user_id=str(uuid4()), role="viewer",
    )
    try:
        response = await client.get(f"{BASE}/metrics")
        assert response.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_tenant, None)
