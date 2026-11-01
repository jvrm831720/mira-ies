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
            self.statements = []

        async def execute(self, *args, **kwargs):
            self.execute_count += 1
            self.statements.append(args[0])
            return await self.wrapped.execute(*args, **kwargs)

    session = CountingSession(db_session)
    batches = [batch async for batch in iter_student_group_batches(session, tenant_id=tenant[0].id)]
    assert len(batches) == 1
    assert len(batches[0].students) == 3
    assert session.execute_count == 2  # one student query + one tenant-scoped history query
    history_sql = str(session.statements[1]).lower()
    assert "row_number() over" in history_sql
    assert "student_history_rank" in history_sql


@pytest.mark.asyncio
async def test_student_group_detail_for_all_seven_groups(client, auth_headers, db_session, tenant):
    await _seed_student(
        db_session,
        tenant,
        matricula="DETAIL",
        nome="Aluna Detalhe",
        risk_level="critico",
        risk_score=92,
        dias_atraso_boleto=30,
        dias_sem_login=25,
    )
    group_ids = [
        "risk_critical",
        "risk_medium",
        "financial_delay",
        "days_without_login_elevated",
        "risk_increase",
        "multiple_active_signals",
        "missing_score",
    ]
    for group_id in group_ids:
        response = await client.get(f"/api/v1/student-groups/{group_id}", headers=auth_headers)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["id"] == group_id
        assert body["catalog_version"] == "1.0.0"
        assert body["inclusion_rule"]
        assert body["metrics"]["total_eligible"] == 1
        assert body["metrics"]["total_evaluated"] == 1
        assert body["evaluated_at"]
        if group_id == "missing_score":
            assert "não baixo risco" in body["inclusion_rule"]


@pytest.mark.asyncio
async def test_detail_metrics_match_existing_summary(client, auth_headers, db_session, tenant):
    await _seed_student(
        db_session,
        tenant,
        matricula="METRIC",
        risk_level="critico",
        risk_score=91,
        dias_atraso_boleto=20,
    )
    summary_response = await client.get("/api/v1/student-groups/summary", headers=auth_headers)
    detail_response = await client.get(
        "/api/v1/student-groups/risk_critical", headers=auth_headers
    )
    assert summary_response.status_code == detail_response.status_code == 200
    summary_group = next(
        item for item in summary_response.json()["groups"] if item["id"] == "risk_critical"
    )
    metrics = detail_response.json()["metrics"]
    assert metrics["total_belonging"] == summary_group["matched_count"]
    assert metrics["total_not_belonging"] == summary_group["false_count"]
    assert metrics["total_indeterminate"] == summary_group["indeterminate_count"]


@pytest.mark.asyncio
async def test_members_are_true_only_and_explain_real_signals(client, auth_headers, db_session, tenant):
    member = await _seed_student(
        db_session,
        tenant,
        matricula="MEMBER",
        nome="Pessoa Membro",
        risk_level="critico",
        risk_score=90,
        dias_atraso_boleto=18,
        dias_sem_login=None,
    )
    await _seed_student(
        db_session,
        tenant,
        matricula="UNKNOWN",
        nome="Pessoa Incerta",
        risk_level=None,
        risk_score=None,
        dias_atraso_boleto=None,
    )
    await _seed_student(
        db_session,
        tenant,
        matricula="INACTIVE",
        nome="Pessoa Inativa",
        risk_level="critico",
        risk_score=88,
        is_active=False,
    )

    response = await client.get(
        "/api/v1/student-groups/multiple_active_signals/members?limit=10",
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["count"] == 1
    item = body["members"][0]
    assert item["student_id"] == member.id
    assert item["name"] == "Pessoa Membro"
    assert item["membership_status"] == "TRUE"
    assert {signal["signal_id"] for signal in item["matched_signals"]} == {
        "risk_critical",
        "financial_delay",
    }
    signal_states = {signal["signal_id"]: signal["status"] for signal in item["signals"]}
    assert signal_states["days_without_login_elevated"] == "INDETERMINATE"
    assert item["evidence"]["active_count"] == 2
    assert "missing_score" not in signal_states
    assert not {"matricula", "email", "telefone", "saldo_devedor"} & item.keys()
    assert body["has_more"] is False


@pytest.mark.asyncio
async def test_missing_score_explains_coverage_gap_not_low_risk(client, auth_headers, db_session, tenant):
    student = await _seed_student(
        db_session,
        tenant,
        matricula="NO-SCORE",
        nome="Pessoa Sem Score",
        risk_level=None,
        risk_score=None,
    )
    response = await client.get(
        "/api/v1/student-groups/missing_score/members", headers=auth_headers
    )
    assert response.status_code == 200
    item = response.json()["members"][0]
    assert item["student_id"] == student.id
    assert item["matched_signals"][0]["status"] == "TRUE"
    assert item["matched_signals"][0]["evidence"]["has_usable_score"] is False
    assert "não indica baixo risco" in item["matched_signals"][0]["evidence"]["note"].lower()


@pytest.mark.asyncio
async def test_members_paginate_with_cursor_without_duplicates(client, auth_headers, db_session, tenant):
    students = []
    for index in range(3):
        students.append(
            await _seed_student(
                db_session,
                tenant,
                matricula=f"PAGE-{index}",
                nome=f"Página {index}",
                risk_level="critico",
                risk_score=80 + index,
            )
        )
    first = await client.get(
        "/api/v1/student-groups/risk_critical/members?limit=2", headers=auth_headers
    )
    assert first.status_code == 200
    first_body = first.json()
    assert first_body["count"] == 2
    assert first_body["has_more"] is True
    assert first_body["next_cursor"]

    second = await client.get(
        f"/api/v1/student-groups/risk_critical/members?cursor={first_body['next_cursor']}",
        headers=auth_headers,
    )
    assert second.status_code == 200
    second_body = second.json()
    assert second_body["count"] == 1
    page_one_ids = {row["student_id"] for row in first_body["members"]}
    page_two_ids = {row["student_id"] for row in second_body["members"]}
    assert not page_one_ids & page_two_ids
    assert page_one_ids | page_two_ids == {student.id for student in students}
    assert first_body["ordering"] == "student_id_ascending"
    changed_page_size = await client.get(
        f"/api/v1/student-groups/risk_critical/members?limit=3&cursor={first_body['next_cursor']}",
        headers=auth_headers,
    )
    assert changed_page_size.status_code == 400


@pytest.mark.asyncio
async def test_cursor_rejects_tampering_wrong_tenant_and_wrong_group(
    client, tenant_factory, db_session
):
    tenant_a, key_a = await tenant_factory(slug="cursor-a", name="Cursor A")
    tenant_b, key_b = await tenant_factory(slug="cursor-b", name="Cursor B")
    for index in range(2):
        await _seed_student(
            db_session,
            (tenant_a, key_a),
            matricula=f"CURSOR-A-{index}",
            risk_level="critico",
            risk_score=90,
        )
    first = await client.get(
        "/api/v1/student-groups/risk_critical/members?limit=1",
        headers={"X-API-Key": key_a},
    )
    token = first.json()["next_cursor"]
    assert token

    tampered = await client.get(
        f"/api/v1/student-groups/risk_critical/members?cursor={token}x",
        headers={"X-API-Key": key_a},
    )
    cross_group = await client.get(
        f"/api/v1/student-groups/risk_medium/members?cursor={token}",
        headers={"X-API-Key": key_a},
    )
    cross_tenant = await client.get(
        f"/api/v1/student-groups/risk_critical/members?cursor={token}",
        headers={"X-API-Key": key_b},
    )
    assert tampered.status_code == 400
    assert cross_group.status_code == 400
    assert cross_tenant.status_code == 400


@pytest.mark.asyncio
async def test_expired_cursor_returns_controlled_error(client, auth_headers):
    import time

    from app.student_groups.pagination import create_group_cursor

    token = create_group_cursor(
        tenant_id="not-the-authenticated-tenant",
        group_id="risk_critical",
        after_id="student-id",
        last_member_id="student-id",
        limit=10,
        now=int(time.time()) - 3601,
    )
    response = await client.get(
        f"/api/v1/student-groups/risk_critical/members?cursor={token}",
        headers=auth_headers,
    )
    assert response.status_code == 400  # binding is checked before expiry


@pytest.mark.asyncio
async def test_cursor_expiration_is_reported_after_valid_tenant_binding(
    client, auth_headers, tenant
):
    import time

    from app.student_groups.pagination import create_group_cursor

    token = create_group_cursor(
        tenant_id=tenant[0].id,
        group_id="risk_critical",
        after_id="student-id",
        last_member_id="student-id",
        limit=10,
        now=int(time.time()) - 3601,
    )
    response = await client.get(
        f"/api/v1/student-groups/risk_critical/members?cursor={token}",
        headers=auth_headers,
    )
    assert response.status_code == 410
    assert "expirado" in response.json()["detail"]


@pytest.mark.asyncio
async def test_member_scope_ignores_tenant_query_and_hides_other_tenant(
    client, tenant_factory, db_session
):
    tenant_a, key_a = await tenant_factory(slug="members-a", name="Members A")
    tenant_b, key_b = await tenant_factory(slug="members-b", name="Members B")
    await _seed_student(
        db_session,
        (tenant_a, key_a),
        matricula="PRIVATE-A",
        nome="Somente A",
        risk_level="critico",
        risk_score=90,
    )
    student_b = await _seed_student(
        db_session,
        (tenant_b, key_b),
        matricula="PRIVATE-B",
        nome="Somente B",
        risk_level="critico",
        risk_score=90,
    )
    response = await client.get(
        f"/api/v1/student-groups/risk_critical/members?tenant_id={tenant_b.id}",
        headers={"X-API-Key": key_a},
    )
    assert response.status_code == 200
    assert {row["name"] for row in response.json()["members"]} == {"Somente A"}
    assert student_b.id not in {row["student_id"] for row in response.json()["members"]}


@pytest.mark.asyncio
async def test_detail_and_members_require_auth_and_unknown_group_is_404(client, auth_headers):
    assert (await client.get("/api/v1/student-groups/risk_critical")).status_code == 401
    assert (
        await client.get("/api/v1/student-groups/risk_critical/members")
    ).status_code == 401
    missing = await client.get("/api/v1/student-groups/not-a-group", headers=auth_headers)
    assert missing.status_code == 404
    empty_cursor = await client.get(
        "/api/v1/student-groups/risk_critical/members?cursor=", headers=auth_headers
    )
    oversized_page = await client.get(
        "/api/v1/student-groups/risk_critical/members?limit=101", headers=auth_headers
    )
    assert empty_cursor.status_code == 400
    assert oversized_page.status_code == 422


@pytest.mark.asyncio
async def test_user_below_viewer_role_cannot_access_group_routes(
    client, tenant, monkeypatch
):
    from app.core import auth as auth_module
    from app.main import app

    low_role_context = auth_module.AuthContext(
        tenant=tenant[0],
        tenant_id=tenant[0].id,
        tenant_slug=tenant[0].slug,
        role="guest",
    )

    async def guest_context():
        return low_role_context

    app.dependency_overrides[auth_module.get_current_tenant] = guest_context
    try:
        detail = await client.get("/api/v1/student-groups/risk_critical")
        members = await client.get("/api/v1/student-groups/risk_critical/members")
    finally:
        app.dependency_overrides.pop(auth_module.get_current_tenant, None)
    assert detail.status_code == 403
    assert members.status_code == 403


@pytest.mark.asyncio
async def test_member_pagination_stops_after_lookahead_instead_of_loading_population(
    client, auth_headers, db_session, tenant, monkeypatch
):
    from app.api import student_groups as api_module
    from app.models.student import Student, UploadBatch

    batch = UploadBatch(
        tenant_id=tenant[0].id,
        filename="stream-test.csv",
        original_filename="stream-test.csv",
        status="processed",
        total_rows=60,
        processed_rows=60,
    )
    db_session.add(batch)
    await db_session.flush()
    db_session.add_all(
        [
            Student(
                batch_id=batch.id,
                tenant_id=tenant[0].id,
                matricula=f"STREAM-{index}",
                nome=f"Aluno Stream {index}",
                risk_level="critico",
                risk_score=90,
                is_active=True,
            )
            for index in range(60)
        ]
    )
    await db_session.commit()

    original_iterator = api_module.iter_student_group_batches
    loaded_ids = []

    async def tracking_batches(db, **kwargs):
        async for batch in original_iterator(db, **kwargs):
            loaded_ids.extend(student.id for student in batch.students)
            yield batch

    monkeypatch.setattr(api_module, "iter_student_group_batches", tracking_batches)
    response = await client.get(
        "/api/v1/student-groups/risk_critical/members?limit=1", headers=auth_headers
    )
    assert response.status_code == 200, response.text
    assert response.json()["count"] == 1
    assert response.json()["has_more"] is True
    assert len(loaded_ids) == 50  # a bounded evaluation batch, not all 60 students
    assert len(loaded_ids) < 60


@pytest.mark.asyncio
async def test_detail_evaluation_failure_is_not_reported_as_zero(client, auth_headers, monkeypatch):
    from app.api import student_groups as api_module

    async def broken_iterator(*args, **kwargs):
        if False:
            yield None
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(api_module, "iter_student_group_batches", broken_iterator)
    response = await client.get("/api/v1/student-groups/risk_critical", headers=auth_headers)
    assert response.status_code == 503
    assert "não foi possível" in response.json()["detail"].lower()
