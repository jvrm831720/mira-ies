"""Testes de integração PostgreSQL da API de grupos virtuais."""
from __future__ import annotations

import pytest

from app.student_groups.loading import iter_student_group_batches
from tests.test_signals_api import _seed_student


@pytest.mark.asyncio
async def test_student_groups_catalog_requires_viewer_auth(client):
    assert (await client.get("/api/v1/student-groups/catalog")).status_code == 401


@pytest.mark.asyncio
async def test_student_groups_catalog_has_exactly_seven(client, auth_headers):
    response = await client.get("/api/v1/student-groups/catalog", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 7
    assert {item["id"] for item in body["groups"]} == {
        "risk_critical",
        "risk_medium",
        "financial_delay",
        "days_without_login_elevated",
        "risk_increase",
        "multiple_active_signals",
        "missing_score",
    }


@pytest.mark.asyncio
async def test_summary_counts_active_students_and_indeterminate(client, auth_headers, tenant, db_session):
    await _seed_student(
        db_session,
        tenant,
        matricula="ACTIVE",
        risk_level="critico",
        risk_score=90,
        dias_atraso_boleto=20,
        dias_sem_login=30,
    )
    await _seed_student(
        db_session,
        tenant,
        matricula="INACTIVE",
        risk_level="critico",
        risk_score=90,
        is_active=False,
    )
    response = await client.get("/api/v1/student-groups/summary", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total_eligible"] == 1
    assert body["evaluated"] == 1
    assert body["truncated"] is False
    groups = {item["id"]: item for item in body["groups"]}
    assert groups["risk_critical"]["matched_count"] == 1
    assert groups["multiple_active_signals"]["matched_count"] == 1
    assert groups["missing_score"]["matched_count"] == 0


@pytest.mark.asyncio
async def test_summary_does_not_cross_tenants(client, tenant_factory, db_session):
    tenant_a, key_a = await tenant_factory(slug="groups-a", name="Groups A")
    tenant_b, key_b = await tenant_factory(slug="groups-b", name="Groups B")
    await _seed_student(db_session, (tenant_a, key_a), matricula="A", risk_level="critico", risk_score=95)
    await _seed_student(db_session, (tenant_b, key_b), matricula="B", risk_level="medio", risk_score=55)
    response_a = await client.get("/api/v1/student-groups/summary", headers={"X-API-Key": key_a})
    response_b = await client.get("/api/v1/student-groups/summary", headers={"X-API-Key": key_b})
    assert response_a.status_code == response_b.status_code == 200
    groups_a = {item["id"]: item for item in response_a.json()["groups"]}
    groups_b = {item["id"]: item for item in response_b.json()["groups"]}
    assert groups_a["risk_critical"]["matched_count"] == 1
    assert groups_a["risk_medium"]["matched_count"] == 0
    assert groups_b["risk_critical"]["matched_count"] == 0
    assert groups_b["risk_medium"]["matched_count"] == 1


@pytest.mark.asyncio
async def test_client_tenant_query_cannot_change_scope(client, auth_headers, tenant, db_session):
    # A claimed query parameter is intentionally ignored; scope comes only from auth.
    await _seed_student(db_session, tenant, matricula="ONLY", risk_level="critico", risk_score=90)
    response = await client.get(
        "/api/v1/student-groups/summary?tenant_id=another-tenant",
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["total_eligible"] == 1


@pytest.mark.asyncio
async def test_history_queries_are_batched_not_one_per_student(tenant, db_session):
    for index in range(3):
        await _seed_student(
            db_session,
            tenant,
            matricula=f"BATCH-{index}",
            risk_level="baixo",
            risk_score=20,
        )

    class CountingSession:
        def __init__(self, wrapped):
            self.wrapped = wrapped
            self.execute_count = 0

        async def execute(self, *args, **kwargs):
            self.execute_count += 1
            return await self.wrapped.execute(*args, **kwargs)

    session = CountingSession(db_session)
    batches = [batch async for batch in iter_student_group_batches(session, tenant_id=tenant[0].id)]
    assert len(batches) == 1
    assert len(batches[0].students) == 3
    assert session.execute_count == 2  # one student query + one tenant-scoped history query
