"""Wave 5: PostgreSQL-backed four-view inbox and serialized, idempotent human actions."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.api.work_inbox import (
    ClaimBody, ResolveBody, _priority_order, claim_work_activity, priority_reasons,
    resolve_work_activity, work_inbox, work_inbox_counts,
)
from app.db.session import AsyncSessionLocal
from app.models.auth import User
from app.models.work_activity import WorkActivity, WorkActivityEvent


def auth(tenant: str, user: str | None, session: str | None = "active"):
    return SimpleNamespace(tenant_id=tenant, user_id=user, session_id=session, role="operator")


async def seed_user(db, tenant_id: str, alias: str):
    user = User(
        tenant_id=tenant_id, email=f"work5-{alias}-{uuid4()}@example.test",
        display_name=alias, password_hash="not-used", role="operator", is_active=True,
    )
    db.add(user)
    await db.flush()
    return user.id


async def seed_activity(db, tenant_id: str, assignee: str | None, *,
                        priority: str = "normal", status: str = "open",
                        due_at: datetime | None = None):
    item = WorkActivity(
        tenant_id=tenant_id, title="Atividade humana " + str(uuid4())[:8],
        priority=priority, assignee_user_id=assignee, status=status,
        due_at=due_at, origin_type="manual",
    )
    db.add(item)
    await db.flush()
    return item.id


@pytest.mark.asyncio
async def test_four_perspectives_paging_priority_and_tenant_scope(tenant_factory, db_session):
    tenant_a, _ = await tenant_factory(slug="work5-perspectives-a")
    tenant_b, _ = await tenant_factory(slug="work5-perspectives-b")
    a, b = tenant_a.id, tenant_b.id
    owner = await seed_user(db_session, a, "owner")
    colleague = await seed_user(db_session, a, "colleague")
    foreign = await seed_user(db_session, b, "foreign")
    await seed_activity(db_session, b, foreign, priority="urgent")
    overdue = await seed_activity(
        db_session, a, owner, priority="urgent",
        due_at=datetime.now(timezone.utc) - timedelta(hours=3),
    )
    for n in range(28):
        await seed_activity(db_session, a, owner, priority="normal")
    await seed_activity(db_session, a, colleague)
    await seed_activity(db_session, a, None)
    await seed_activity(db_session, a, owner, status="completed")
    await db_session.commit()
    current = auth(a, owner)

    page = await work_inbox(view="mine", limit=25, offset=0, auth=current, db=db_session)
    assert page["total"] == 29 and len(page["items"]) == 25
    assert page["has_more"] is True and page["next_offset"] == 25
    assert page["items"][0]["id"] == overdue
    assert {"manual_priority", "overdue"}.issubset(
        {reason["code"] for reason in page["items"][0]["priority_reasons"]}
    )
    next_page = await work_inbox(view="mine", limit=25, offset=25, auth=current, db=db_session)
    assert next_page["total"] == 29 and len(next_page["items"]) == 4
    assert not next_page["has_more"]
    assert not ({row["id"] for row in page["items"]} & {row["id"] for row in next_page["items"]})

    counts = (await work_inbox_counts(auth=current, db=db_session))["counts"]
    assert counts == {"mine": 29, "team": 1, "unassigned": 1, "history": 1}
    assert (await work_inbox(view="team", limit=25, offset=0, auth=current, db=db_session))["total"] == 1
    assert (await work_inbox(view="unassigned", limit=25, offset=0, auth=current, db=db_session))["total"] == 1
    assert (await work_inbox(view="history", limit=25, offset=0, auth=current, db=db_session))["total"] == 1
    assert all(row["tenant_id"] == a for row in page["items"])

    with pytest.raises(HTTPException) as denied:
        await work_inbox(view="mine", limit=25, offset=0, auth=auth(a, None), db=db_session)
    assert denied.value.status_code == 403


@pytest.mark.asyncio
async def test_claim_resolve_result_replay_conflict_and_audit(tenant_factory, db_session):
    tenant, _ = await tenant_factory(slug="work5-human-results")
    tenant_id = tenant.id
    owner = await seed_user(db_session, tenant_id, "owner")
    colleague = await seed_user(db_session, tenant_id, "colleague")
    unassigned = await seed_activity(db_session, tenant_id, None)
    occupied = await seed_activity(db_session, tenant_id, colleague)
    await db_session.commit()
    human = auth(tenant_id, owner)
    claim_key = str(uuid4()).replace("-", "")

    with pytest.raises(HTTPException) as occupied_error:
        await claim_work_activity(
            occupied, ClaimBody(expected_revision=1, operation_key=str(uuid4()).replace("-", "")),
            auth=human, db=db_session,
        )
    assert occupied_error.value.status_code == 409

    first = await claim_work_activity(
        unassigned, ClaimBody(expected_revision=1, operation_key=claim_key),
        auth=human, db=db_session,
    )
    assert first["activity"]["assignee_user_id"] == owner
    assert first["activity"]["revision"] == 2
    await assert_audit(db_session, tenant_id, unassigned, "claimed", 1)
    replay = await claim_work_activity(
        unassigned, ClaimBody(expected_revision=1, operation_key=claim_key),
        auth=human, db=db_session,
    )
    assert replay["idempotent_replay"] and replay["event_id"] == first["event_id"]

    with pytest.raises(HTTPException) as stale:
        await resolve_work_activity(
            unassigned, ResolveBody(expected_revision=1, operation_key=str(uuid4()).replace("-", ""),
                                    kind="done", note="Tentativa humana"),
            auth=human, db=db_session,
        )
    assert stale.value.status_code == 409

    result_key = str(uuid4()).replace("-", "")
    resolved = await resolve_work_activity(
        unassigned, ResolveBody(expected_revision=2, operation_key=result_key,
                                kind="unreachable", note="Telefone indisponível; tentativa encerrada"),
        auth=human, db=db_session,
    )
    assert resolved["activity"]["status"] == "completed"
    assert resolved["activity"]["revision"] == 3
    assert resolved["activity"]["completed_at"] is not None
    await assert_audit(db_session, tenant_id, unassigned, "human_result_resolved", 1)
    unchanged = await resolve_work_activity(
        unassigned, ResolveBody(expected_revision=2, operation_key=result_key,
                                kind="unreachable", note="Telefone indisponível; tentativa encerrada"),
        auth=human, db=db_session,
    )
    assert unchanged["idempotent_replay"] and unchanged["event_id"] == resolved["event_id"]
    with pytest.raises(HTTPException) as duplicate_diff:
        await resolve_work_activity(
            unassigned, ResolveBody(expected_revision=2, operation_key=result_key,
                                    kind="done", note="Resultado diferente"),
            auth=human, db=db_session,
        )
    assert duplicate_diff.value.status_code == 409
    await assert_audit(db_session, tenant_id, unassigned, "human_result_resolved", 1)

    with pytest.raises(HTTPException) as foreign_owner:
        await resolve_work_activity(
            occupied, ResolveBody(expected_revision=1, operation_key=str(uuid4()).replace("-", ""),
                                  kind="done", note="Tentativa de outro responsável"),
            auth=human, db=db_session,
        )
    assert foreign_owner.value.status_code == 403


async def assert_audit(db, tenant: str, activity: str, kind: str, count: int):
    rows = (await db.execute(select(WorkActivityEvent).where(
        WorkActivityEvent.tenant_id == tenant,
        WorkActivityEvent.activity_id == activity,
        WorkActivityEvent.event_type == kind,
    ))).scalars().all()
    assert len(rows) == count
    if kind == "human_result_resolved":
        assert rows[0].payload["domain"] == "human_work"
        assert rows[0].payload["kind"] in {"done", "unreachable", "deferred", "referred"}


@pytest.mark.asyncio
async def test_deferred_stays_open_and_requires_future_date(tenant_factory, db_session):
    tenant, _ = await tenant_factory(slug="work5-defer")
    tenant_id = tenant.id
    human_id = await seed_user(db_session, tenant_id, "defer")
    activity = await seed_activity(db_session, tenant_id, human_id, status="in_progress")
    await db_session.commit()

    with pytest.raises(ValueError):
        ResolveBody(expected_revision=1, operation_key="12345678", kind="deferred", note="Falta prazo")
    new_due = datetime.now(timezone.utc) + timedelta(days=2)
    changed = await resolve_work_activity(
        activity, ResolveBody(expected_revision=1, operation_key=str(uuid4()).replace("-", ""),
                              kind="deferred", note="Aguardando retorno humano", next_due_at=new_due),
        auth=auth(tenant_id, human_id), db=db_session,
    )
    assert changed["activity"]["status"] == "open"
    assert changed["activity"]["completed_at"] is None
    assert changed["activity"]["due_at"] is not None
    await assert_audit(db_session, tenant_id, activity, "human_result_resolved", 1)


@pytest.mark.asyncio
async def test_concurrent_resolution_uses_for_update_and_revision(tenant_factory, db_session):
    tenant, _ = await tenant_factory(slug="work5-concurrency")
    tenant_id = tenant.id
    user_id = await seed_user(db_session, tenant_id, "concurrent")
    activity = await seed_activity(db_session, tenant_id, user_id)
    await db_session.commit()

    async def compete(key: str, note: str):
        async with AsyncSessionLocal() as db:
            try:
                value = await resolve_work_activity(
                    activity, ResolveBody(expected_revision=1, operation_key=key,
                                          kind="done", note=note),
                    auth=auth(tenant_id, user_id), db=db,
                )
                return value["idempotent_replay"]
            except HTTPException as exc:
                await db.rollback()
                return exc.status_code

    result = await asyncio.gather(
        compete(str(uuid4()).replace("-", ""), "Operador A"),
        compete(str(uuid4()).replace("-", ""), "Operador B"),
    )
    assert sorted(result, key=str) == sorted([False, 409], key=str)
    await assert_audit(db_session, tenant_id, activity, "human_result_resolved", 1)


@pytest.mark.asyncio
async def test_inbox_denies_service_api_keys_without_a_human_session(client, tenant_factory):
    _, key = await tenant_factory(slug="work5-no-service-claim")
    headers = {"X-API-Key": key}
    response = await client.get("/api/v1/work/inbox?view=mine", headers=headers)
    assert response.status_code == 403
    count = await client.get("/api/v1/work/inbox/counts", headers=headers)
    assert count.status_code == 403
    claim = await client.post(
        f"/api/v1/work/activities/{uuid4()}/claim", headers=headers,
        json={"expected_revision": 1, "operation_key": str(uuid4()).replace("-", "")},
    )
    assert claim.status_code == 403


def test_priority_reasons_are_documented_signals_not_recovery_scores():
    now = datetime.now(timezone.utc)
    row = SimpleNamespace(priority="urgent", due_at=now - timedelta(hours=2),
                          status="open", assignee_user_id=None, origin_type="campaign")
    codes = {reason["code"] for reason in priority_reasons(row, now)}
    assert codes == {"manual_priority", "overdue", "unassigned", "campaign_source"}
    assert "recovery" not in " ".join(codes)
