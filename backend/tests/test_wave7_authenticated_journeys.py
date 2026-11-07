"""Wave 7: six signed MFA + real-ASGI + PostgreSQL API journeys.

These are integration acceptance tests, not mocked browser screenshots. The
separate Playwright gate proves desktop/mobile UI on top of this authenticated
backend. Payments, dispatch and campaign execution remain untouched.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError

from app.core.user_sessions import create_user_session
from app.models.auth import User
from app.models.object_view import ObjectView
from app.models.organization import ModuleEntitlement
from app.models.retention_campaign import RetentionCampaignProposal
from app.models.student import Student, UploadBatch
from app.models.work_activity import WorkActivity, WorkActivityEvent
from app.services.dispatch_core import bind_tenant
from app.services.federated_search_providers import PROVIDERS


async def _seed_tenant(db, tenant, label: str):
    tenant.segment = "institution"
    db.add_all([
        ModuleEntitlement(tenant_id=tenant.id, module_key=module,
                          status="enabled", source="test")
        for module in ("workspace", "permanence", "billing")
    ])
    batch = UploadBatch(tenant_id=tenant.id, filename="wave7.csv",
                        original_filename="wave7.csv", status="processed")
    user = User(
        tenant_id=tenant.id, display_name="Homologação " + label,
        email=f"wave7-{label}-{uuid4()}@example.test",
        password_hash="not-a-real-password", role="coordinator",
        is_active=True, mfa_enabled_at=datetime.now(timezone.utc),
        onboarding_completed_at=datetime.now(timezone.utc),
    )
    viewer = User(
        tenant_id=tenant.id, display_name="Leitor " + label,
        email=f"wave7-viewer-{label}-{uuid4()}@example.test",
        password_hash="not-a-real-password", role="viewer",
        is_active=True, mfa_enabled_at=datetime.now(timezone.utc),
    )
    db.add_all([batch, user, viewer])
    await db.flush()
    student = Student(
        tenant_id=tenant.id, batch_id=batch.id, matricula="W7-" + label,
        nome="Aline Homologacao " + label,
        curso="Engenharia", risk_score=83, risk_level="critico",
        communication_preferences={}, behavior_properties={},
    )
    db.add(student)
    await db.flush()
    task = WorkActivity(
        tenant_id=tenant.id, title="Revisar caso Aline " + label,
        status="open", priority="high", origin_type="manual",
        assignee_user_id=None, student_id=student.id,
    )
    view = ObjectView(
        tenant_id=tenant.id, owner_user_id=user.id, object_key="students",
        scope="personal", revision=1, config_version=1,
        name="View Aline " + label,
        config={"version": 1, "columns": ["nome", "matricula"]},
        is_sensitive=False,
    )
    proposal = RetentionCampaignProposal(
        tenant_id=tenant.id, title="Campanha Aline " + label, status="draft",
        source_group_ids=[], source_catalog_version="v1",
        recommendation_engine="manual", source_evaluated_at=datetime.now(timezone.utc),
        objective="Acompanhamento humano", strategy="Sem disparos",
        recommended_channels=["operacao_interna"], cadence_days=[0],
        message_brief="Atividade interna", audience_snapshot=[], audience_hash="0" * 64,
        audience_total=0, outreach_eligible_count=0, blocked_count=0,
        internal_action_count=0,
    )
    db.add_all([task, view, proposal])
    await db.commit()
    token, _ = await create_user_session(db, user, tenant, aal=2)
    viewer_token, _ = await create_user_session(db, viewer, tenant, aal=2)
    await db.commit()
    await bind_tenant(db, tenant.id)
    case_id = str(uuid4())
    await db.execute(text("""
        INSERT INTO dispatch_obligations (
            id, tenant_id, external_ref, subject_type, subject_ref,
            status, balance, source, source_version, evidence_ref, verified_at
        )
        VALUES (:id, :tenant, :ref, 'student', :subject, 'open', 149.90,
                'wave7_synthetic', 1, 'test-only', :verified)
    """), {
        "id": case_id, "tenant": tenant.id, "ref": "W7-FIN-Aline-" + label,
        "subject": student.matricula, "verified": datetime.now(timezone.utc),
    })
    await db.commit()
    return {
        "tenant": tenant.id, "student": student.id,
        "task": task.id, "view": view.id, "campaign": proposal.id,
        "case": case_id, "token": token, "viewer_token": viewer_token,
    }


@pytest_asyncio.fixture
async def live_workspaces(db_session, tenant_factory):
    await db_session.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
    await db_session.commit()
    a, _ = await tenant_factory(slug="wave7-e2e-a")
    b, _ = await tenant_factory(slug="wave7-e2e-b")
    first = await _seed_tenant(db_session, a, "A")
    second = await _seed_tenant(db_session, b, "B")
    return first, second


def headers(token: str) -> dict:
    return {"Authorization": "Bearer " + token}


@pytest.mark.asyncio
async def test_journey_01_app_shell_authenticated_workspace_and_roles(
    client, live_workspaces
):
    a, b = live_workspaces
    own = await client.get("/api/v1/org/me", headers=headers(a["token"]))
    assert own.status_code == 200, own.text
    assert own.json()["tenant_id"] == a["tenant"]
    assert "billing" in own.json()["enabled_modules"]
    assert "permanence" in own.json()["enabled_modules"]
    assert own.json()["operation_profile"] == "institution"
    foreign = await client.get("/api/v1/org/me", headers=headers(b["token"]))
    assert foreign.status_code == 200 and foreign.json()["tenant_id"] == b["tenant"]
    unauthorized = await client.get("/api/v1/org/me")
    assert unauthorized.status_code in (401, 403)


@pytest.mark.asyncio
async def test_journey_02_object_index_and_authorized_saved_views(
    client, live_workspaces
):
    a, b = live_workspaces
    listing = await client.get(
        "/api/v1/object-index/students?q=Homologacao&limit=2",
        headers=headers(a["token"]),
    )
    assert listing.status_code == 200, listing.text
    payload = listing.json()
    assert payload["total"] == 1 and payload["students"][0]["id"] == a["student"]
    assert b["student"] not in str(payload)
    views = await client.get(
        "/api/v1/object-views?object_key=students",
        headers=headers(a["token"]),
    )
    assert views.status_code == 200, views.text
    assert [entry["id"] for entry in views.json()["views"]] == [a["view"]]
    viewer = await client.get(
        "/api/v1/object-index/students?sort=risk_desc",
        headers=headers(a["viewer_token"]),
    )
    assert viewer.status_code == 403
    # Personal views cannot leak to another human session or workspace.
    foreign = await client.get(
        "/api/v1/object-views/" + a["view"], headers=headers(b["token"]),
    )
    assert foreign.status_code in (403, 404)


@pytest.mark.asyncio
async def test_journey_03_student_360_uses_domain_permissions(
    client, live_workspaces
):
    a, b = live_workspaces
    own = await client.get(
        f"/api/v1/students/{a['student']}/risk", headers=headers(a["token"]),
    )
    assert own.status_code == 200, own.text
    assert a["student"] in str(own.json())
    forbidden = await client.get(
        f"/api/v1/students/{b['student']}/risk", headers=headers(a["token"]),
    )
    assert forbidden.status_code in (403, 404)
    reduced = await client.get(
        f"/api/v1/students/{a['student']}/risk",
        headers=headers(a["viewer_token"]),
    )
    assert reduced.status_code in (200, 403)
    if reduced.status_code == 200:
        # Viewer projection cannot contain raw sensitive model scores.
        assert "shap_top_factors" not in reduced.json()
    assert forbidden.status_code != 200


@pytest.mark.asyncio
async def test_journey_04_financial_360_read_only_and_tenant_isolated(
    client, live_workspaces
):
    a, b = live_workspaces
    items = await client.get(
        "/api/v1/collections/cases?q=W7-FIN&limit=5",
        headers=headers(a["token"]),
    )
    assert items.status_code == 200, items.text
    assert items.json()["total"] == 1
    detail = await client.get(
        f"/api/v1/collections/cases/{a['case']}", headers=headers(a["token"]),
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["case"]["id"] == a["case"]
    assert detail.json()["case"]["balance"] == "149.90"
    assert not detail.json()["payment_events"]
    foreign = await client.get(
        f"/api/v1/collections/cases/{b['case']}", headers=headers(a["token"]),
    )
    assert foreign.status_code == 404
    denied = await client.get(
        "/api/v1/collections/cases", headers=headers(a["viewer_token"]),
    )
    assert denied.status_code == 403


@pytest.mark.asyncio
async def test_journey_05_human_work_claim_resolve_idempotent_without_payment(
    client, db_session, live_workspaces
):
    a, b = live_workspaces
    queue = await client.get(
        "/api/v1/work/inbox?view=unassigned", headers=headers(a["token"]),
    )
    assert queue.status_code == 200, queue.text
    assert a["task"] in {entry["id"] for entry in queue.json()["items"]}
    assert b["task"] not in str(queue.json())
    attempt = await client.post(
        f"/api/v1/work/activities/{a['task']}/resolve",
        headers=headers(a["token"]),
        json={"expected_revision": 1, "operation_key": "denied_before_claim",
              "kind": "done", "note": "Blocked without assignment"},
    )
    assert attempt.status_code == 403
    claim_key = uuid4().hex
    claimed = await client.post(
        f"/api/v1/work/activities/{a['task']}/claim",
        headers=headers(a["token"]),
        json={"expected_revision": 1, "operation_key": claim_key},
    )
    assert claimed.status_code == 200, claimed.text
    assert claimed.json()["activity"]["revision"] == 2
    replay = await client.post(
        f"/api/v1/work/activities/{a['task']}/claim",
        headers=headers(a["token"]),
        json={"expected_revision": 1, "operation_key": claim_key},
    )
    assert replay.status_code == 200 and replay.json()["idempotent_replay"]
    result_key = uuid4().hex
    resolved = await client.post(
        f"/api/v1/work/activities/{a['task']}/resolve",
        headers=headers(a["token"]),
        json={"expected_revision": 2, "operation_key": result_key,
              "kind": "done", "note": "Revisão humana concluída"},
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["activity"]["status"] == "completed"
    again = await client.post(
        f"/api/v1/work/activities/{a['task']}/resolve",
        headers=headers(a["token"]),
        json={"expected_revision": 2, "operation_key": result_key,
              "kind": "done", "note": "Revisão humana concluída"},
    )
    assert again.status_code == 200 and again.json()["idempotent_replay"]
    await bind_tenant(db_session, a["tenant"])
    events = (await db_session.execute(select(func.count(WorkActivityEvent.id)).where(
        WorkActivityEvent.tenant_id == a["tenant"],
        WorkActivityEvent.activity_id == a["task"],
        WorkActivityEvent.event_type == "human_result_resolved",
    ))).scalar_one()
    assert events == 1
    source_status = (await db_session.execute(text("""
        SELECT status FROM dispatch_obligations WHERE tenant_id=:t AND id=:id
    """), {"t": a["tenant"], "id": a["case"]})).scalar_one()
    assert source_status == "open"
    assert not (await db_session.execute(text("""
        SELECT count(*) FROM dispatch_payment_events WHERE tenant_id=:t
    """), {"t": a["tenant"]})).scalar_one()


@pytest.mark.asyncio
async def test_journey_06_federated_search_partial_and_no_cross_tenant(
    client, live_workspaces, monkeypatch
):
    a, b = live_workspaces
    url = "/api/v1/search/universal?q=Aline&limit=5"
    response = await client.get(url, headers=headers(a["token"]))
    assert response.status_code == 200, response.text
    data = response.json()
    assert {result["category"] for result in data["results"]} == {
        "students", "collections", "work", "views", "campaigns",
    }
    assert data["actions_executed"] is False
    assert all(result["kind"] == "navigate" for result in data["results"])
    assert b["student"] not in str(data) and b["case"] not in str(data)

    async def unavailable(_ctx):
        raise SQLAlchemyError("opaque provider outage - do not disclose")
    monkeypatch.setitem(PROVIDERS, "campaigns", unavailable)
    partial = await client.get(url, headers=headers(a["token"]))
    assert partial.status_code == 200 and partial.json()["partial"]
    assert partial.json()["providers"]["campaigns"]["status"] == "unavailable"
    assert "opaque" not in partial.text
    assert any(item["category"] == "students" for item in partial.json()["results"])

    viewer = await client.get(url, headers=headers(a["viewer_token"]))
    assert viewer.status_code == 200
    categories = {item["category"] for item in viewer.json()["results"]}
    assert "collections" not in categories and "work" not in categories
    assert "students" in categories
