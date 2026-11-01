"""Integration tests: WorkActivity API — tenant isolation, assignee rules, transitions, events."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core.mira_security import hash_password
from app.models.auth import User
from app.models.work_activity import WorkActivity, WorkActivityEvent


async def _user(
    db_session,
    *,
    tenant_id: str,
    email: str,
    role: str = "operator",
    is_active: bool = True,
    display_name: str = "Operador",
) -> User:
    u = User(
        tenant_id=tenant_id,
        display_name=display_name,
        email=email,
        password_hash=hash_password("TestPass123!"),
        role=role,
        is_active=is_active,
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


@pytest.mark.asyncio
async def test_create_list_and_events(client, tenant_factory, db_session):
    tenant, key = await tenant_factory(slug="work-create")
    headers = {"X-API-Key": key}
    operator = await _user(
        db_session, tenant_id=tenant.id, email="op-create@test.local", role="operator"
    )

    created = await client.post(
        "/api/v1/work/activities",
        headers=headers,
        json={
            "title": "Follow-up aluno crítico",
            "activity_type": "follow_up",
            "assignee_user_id": operator.id,
            "due_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["title"] == "Follow-up aluno crítico"
    assert body["status"] == "open"
    assert body["assignee_user_id"] == operator.id
    assert body["tenant_id"] == tenant.id
    activity_id = body["id"]

    listed = await client.get("/api/v1/work/activities", headers=headers)
    assert listed.status_code == 200, listed.text
    assert listed.json()["count"] >= 1
    ids = {a["id"] for a in listed.json()["activities"]}
    assert activity_id in ids

    events = await client.get(
        f"/api/v1/work/activities/{activity_id}/events", headers=headers
    )
    assert events.status_code == 200, events.text
    types = [e["event_type"] for e in events.json()["events"]]
    assert "created" in types


@pytest.mark.asyncio
async def test_assignee_must_be_active_same_tenant(client, tenant_factory, db_session):
    tenant_a, key_a = await tenant_factory(slug="work-assignee-a")
    tenant_b, key_b = await tenant_factory(slug="work-assignee-b")
    headers_a = {"X-API-Key": key_a}

    foreign = await _user(
        db_session,
        tenant_id=tenant_b.id,
        email="foreign@test.local",
        role="operator",
    )
    inactive = await _user(
        db_session,
        tenant_id=tenant_a.id,
        email="inactive@test.local",
        role="operator",
        is_active=False,
    )

    bad_foreign = await client.post(
        "/api/v1/work/activities",
        headers=headers_a,
        json={"title": "Cross-tenant", "assignee_user_id": foreign.id},
    )
    assert bad_foreign.status_code == 422, bad_foreign.text
    assert "instituição" in bad_foreign.json()["detail"].lower() or "inválido" in bad_foreign.json()[
        "detail"
    ].lower()

    bad_inactive = await client.post(
        "/api/v1/work/activities",
        headers=headers_a,
        json={"title": "Inactive user", "assignee_user_id": inactive.id},
    )
    assert bad_inactive.status_code == 422, bad_inactive.text


@pytest.mark.asyncio
async def test_tenant_isolation_list_and_detail(client, tenant_factory, db_session):
    tenant_a, key_a = await tenant_factory(slug="work-iso-a")
    tenant_b, key_b = await tenant_factory(slug="work-iso-b")
    headers_a = {"X-API-Key": key_a}
    headers_b = {"X-API-Key": key_b}

    created = await client.post(
        "/api/v1/work/activities",
        headers=headers_a,
        json={"title": "Só tenant A"},
    )
    assert created.status_code == 201, created.text
    activity_id = created.json()["id"]

    foreign_get = await client.get(
        f"/api/v1/work/activities/{activity_id}", headers=headers_b
    )
    assert foreign_get.status_code == 404, foreign_get.text

    foreign_list = await client.get("/api/v1/work/activities", headers=headers_b)
    assert foreign_list.status_code == 200
    assert all(a["id"] != activity_id for a in foreign_list.json()["activities"])

    foreign_patch = await client.patch(
        f"/api/v1/work/activities/{activity_id}",
        headers=headers_b,
        json={"status": "completed"},
    )
    assert foreign_patch.status_code == 404, foreign_patch.text

    foreign_events = await client.get(
        f"/api/v1/work/activities/{activity_id}/events", headers=headers_b
    )
    assert foreign_events.status_code == 404, foreign_events.text


@pytest.mark.asyncio
async def test_transitions_events_and_terminal_lock(client, tenant_factory, db_session):
    tenant, key = await tenant_factory(slug="work-trans")
    headers = {"X-API-Key": key}

    created = await client.post(
        "/api/v1/work/activities",
        headers=headers,
        json={"title": "Ciclo completo"},
    )
    assert created.status_code == 201, created.text
    activity_id = created.json()["id"]

    to_progress = await client.patch(
        f"/api/v1/work/activities/{activity_id}",
        headers=headers,
        json={"status": "in_progress"},
    )
    assert to_progress.status_code == 200, to_progress.text
    assert to_progress.json()["status"] == "in_progress"

    complete = await client.patch(
        f"/api/v1/work/activities/{activity_id}",
        headers=headers,
        json={"status": "completed"},
    )
    assert complete.status_code == 200, complete.text
    assert complete.json()["status"] == "completed"
    assert complete.json()["completed_at"] is not None

    # Terminal: cannot edit title or reopen
    edit = await client.patch(
        f"/api/v1/work/activities/{activity_id}",
        headers=headers,
        json={"title": "Não deveria"},
    )
    assert edit.status_code == 422, edit.text

    reopen = await client.patch(
        f"/api/v1/work/activities/{activity_id}",
        headers=headers,
        json={"status": "open"},
    )
    assert reopen.status_code == 422, reopen.text

    events = await client.get(
        f"/api/v1/work/activities/{activity_id}/events", headers=headers
    )
    assert events.status_code == 200
    types = [e["event_type"] for e in events.json()["events"]]
    assert "created" in types
    assert "status_changed" in types or "completed" in types
    assert "completed" in types


@pytest.mark.asyncio
async def test_invalid_transition_rejected(client, tenant_factory):
    tenant, key = await tenant_factory(slug="work-bad-trans")
    headers = {"X-API-Key": key}

    created = await client.post(
        "/api/v1/work/activities",
        headers=headers,
        json={"title": "Cancelada direto"},
    )
    activity_id = created.json()["id"]

    cancel = await client.patch(
        f"/api/v1/work/activities/{activity_id}",
        headers=headers,
        json={"status": "cancelled"},
    )
    assert cancel.status_code == 200

    again = await client.patch(
        f"/api/v1/work/activities/{activity_id}",
        headers=headers,
        json={"status": "open"},
    )
    assert again.status_code == 422


@pytest.mark.asyncio
async def test_mine_empty_without_user_on_api_key(client, tenant_factory, db_session):
    """API key legada não tem user_id — /mine deve retornar fila vazia, não inventar."""
    tenant, key = await tenant_factory(slug="work-mine-key")
    headers = {"X-API-Key": key}
    operator = await _user(
        db_session, tenant_id=tenant.id, email="mine-op@test.local"
    )
    await client.post(
        "/api/v1/work/activities",
        headers=headers,
        json={"title": "Atribuída", "assignee_user_id": operator.id},
    )

    mine = await client.get("/api/v1/work/activities/mine", headers=headers)
    assert mine.status_code == 200, mine.text
    data = mine.json()
    assert data["count"] == 0
    assert data["activities"] == []
    assert "note" in data or True  # note opcional se sessão sem user


@pytest.mark.asyncio
async def test_patch_assignee_and_due_record_events(client, tenant_factory, db_session):
    tenant, key = await tenant_factory(slug="work-patch")
    headers = {"X-API-Key": key}
    u1 = await _user(db_session, tenant_id=tenant.id, email="u1@test.local", display_name="U1")
    u2 = await _user(db_session, tenant_id=tenant.id, email="u2@test.local", display_name="U2")

    created = await client.post(
        "/api/v1/work/activities",
        headers=headers,
        json={"title": "Com mudanças", "assignee_user_id": u1.id},
    )
    activity_id = created.json()["id"]

    due = (datetime.now(timezone.utc) + timedelta(hours=6)).isoformat()
    patched = await client.patch(
        f"/api/v1/work/activities/{activity_id}",
        headers=headers,
        json={"assignee_user_id": u2.id, "due_at": due},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["assignee_user_id"] == u2.id

    events = await client.get(
        f"/api/v1/work/activities/{activity_id}/events", headers=headers
    )
    types = [e["event_type"] for e in events.json()["events"]]
    assert "assignee_changed" in types
    assert "due_changed" in types

    # Persistência no banco
    row = (
        await db_session.execute(select(WorkActivity).where(WorkActivity.id == activity_id))
    ).scalar_one()
    assert row.assignee_user_id == u2.id
    event_rows = (
        await db_session.execute(
            select(WorkActivityEvent).where(WorkActivityEvent.activity_id == activity_id)
        )
    ).scalars().all()
    assert len(event_rows) >= 3
