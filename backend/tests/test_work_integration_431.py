"""Wave 4.3.1 — filters, relation integrity, timeline, result_recorded."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.core.mira_security import hash_password
from app.models.auth import User
from app.models.intervention import InterventionLog
from app.models.student import Student, UploadBatch
from app.models.work_activity import WorkActivityEvent
from sqlalchemy import select


async def _seed_student(db_session, tenant_id: str, matricula: str = "M-001") -> Student:
    batch = UploadBatch(
        tenant_id=tenant_id,
        filename="t.csv",
        original_filename="t.csv",
        status="processed",
    )
    db_session.add(batch)
    await db_session.flush()
    student = Student(
        tenant_id=tenant_id,
        batch_id=batch.id,
        matricula=matricula,
        nome="Aluno Teste",
        communication_preferences={},
        behavior_properties={},
    )
    db_session.add(student)
    await db_session.commit()
    await db_session.refresh(student)
    return student


async def _seed_log(
    db_session, tenant_id: str, student: Student, status: str = "planned"
) -> InterventionLog:
    log = InterventionLog(
        tenant_id=tenant_id,
        student_id=student.id,
        matricula=student.matricula,
        channel="whatsapp",
        status=status,
        decision_reason="test",
    )
    db_session.add(log)
    await db_session.commit()
    await db_session.refresh(log)
    return log


@pytest.mark.asyncio
async def test_list_filters_student_and_log(client, tenant_factory, db_session):
    tenant, key = await tenant_factory(slug="w431-filter")
    headers = {"X-API-Key": key}
    s1 = await _seed_student(db_session, tenant.id, "F1")
    s2 = await _seed_student(db_session, tenant.id, "F2")
    log1 = await _seed_log(db_session, tenant.id, s1)

    a1 = await client.post(
        "/api/v1/work/activities",
        headers=headers,
        json={
            "title": "A1",
            "student_id": s1.id,
            "intervention_log_id": log1.id,
        },
    )
    assert a1.status_code == 201, a1.text
    a2 = await client.post(
        "/api/v1/work/activities",
        headers=headers,
        json={"title": "A2", "student_id": s2.id},
    )
    assert a2.status_code == 201

    by_student = await client.get(
        f"/api/v1/work/activities?student_id={s1.id}", headers=headers
    )
    assert by_student.status_code == 200
    ids = {x["id"] for x in by_student.json()["activities"]}
    assert a1.json()["id"] in ids
    assert a2.json()["id"] not in ids

    by_log = await client.get(
        f"/api/v1/work/activities?intervention_log_id={log1.id}", headers=headers
    )
    assert by_log.status_code == 200
    assert by_log.json()["count"] == 1
    assert by_log.json()["activities"][0]["id"] == a1.json()["id"]

    combined = await client.get(
        f"/api/v1/work/activities?student_id={s1.id}&intervention_log_id={log1.id}",
        headers=headers,
    )
    assert combined.status_code == 200
    assert combined.json()["count"] == 1


@pytest.mark.asyncio
async def test_block_foreign_student_and_log(client, tenant_factory, db_session):
    ta, key_a = await tenant_factory(slug="w431-a")
    tb, key_b = await tenant_factory(slug="w431-b")
    headers_a = {"X-API-Key": key_a}
    student_b = await _seed_student(db_session, tb.id, "XB")
    log_b = await _seed_log(db_session, tb.id, student_b)

    bad_student = await client.post(
        "/api/v1/work/activities",
        headers=headers_a,
        json={"title": "x", "student_id": student_b.id},
    )
    assert bad_student.status_code == 404

    bad_log = await client.post(
        "/api/v1/work/activities",
        headers=headers_a,
        json={"title": "x", "intervention_log_id": log_b.id},
    )
    assert bad_log.status_code == 404


@pytest.mark.asyncio
async def test_inconsistent_student_log_relation(client, tenant_factory, db_session):
    tenant, key = await tenant_factory(slug="w431-incons")
    headers = {"X-API-Key": key}
    s1 = await _seed_student(db_session, tenant.id, "I1")
    s2 = await _seed_student(db_session, tenant.id, "I2")
    log1 = await _seed_log(db_session, tenant.id, s1)

    bad = await client.post(
        "/api/v1/work/activities",
        headers=headers,
        json={
            "title": "Mismatch",
            "student_id": s2.id,
            "intervention_log_id": log1.id,
        },
    )
    assert bad.status_code == 422
    assert "correspond" in bad.json()["detail"].lower() or "aluno" in bad.json()["detail"].lower()


@pytest.mark.asyncio
async def test_patch_relation_validation(client, tenant_factory, db_session):
    tenant, key = await tenant_factory(slug="w431-patch-rel")
    headers = {"X-API-Key": key}
    s1 = await _seed_student(db_session, tenant.id, "P1")
    s2 = await _seed_student(db_session, tenant.id, "P2")
    log1 = await _seed_log(db_session, tenant.id, s1)

    created = await client.post(
        "/api/v1/work/activities",
        headers=headers,
        json={"title": "Rel", "student_id": s1.id, "intervention_log_id": log1.id},
    )
    assert created.status_code == 201
    aid = created.json()["id"]

    bad = await client.patch(
        f"/api/v1/work/activities/{aid}",
        headers=headers,
        json={"student_id": s2.id},
    )
    assert bad.status_code == 422


@pytest.mark.asyncio
async def test_timeline_empty_and_with_sources(client, tenant_factory, db_session):
    tenant, key = await tenant_factory(slug="w431-tl")
    headers = {"X-API-Key": key}
    student = await _seed_student(db_session, tenant.id, "TL1")

    empty = await client.get(
        f"/api/v1/students/{student.id}/work-timeline", headers=headers
    )
    assert empty.status_code == 200, empty.text
    assert empty.json()["count"] == 0
    assert empty.json()["items"] == []

    log = await _seed_log(db_session, tenant.id, student, status="sent")
    await client.post(
        "/api/v1/work/activities",
        headers=headers,
        json={
            "title": "Follow",
            "student_id": student.id,
            "intervention_log_id": log.id,
        },
    )

    tl = await client.get(
        f"/api/v1/students/{student.id}/work-timeline", headers=headers
    )
    assert tl.status_code == 200
    sources = {i["source"] for i in tl.json()["items"]}
    assert "intervention_log" in sources
    assert "work_activity" in sources
    for item in tl.json()["items"]:
        assert "id" in item and "at" in item and "summary" in item and "refs" in item


@pytest.mark.asyncio
async def test_timeline_no_cross_tenant_leak(client, tenant_factory, db_session):
    ta, key_a = await tenant_factory(slug="w431-tl-a")
    tb, key_b = await tenant_factory(slug="w431-tl-b")
    student_a = await _seed_student(db_session, ta.id, "LA")
    await _seed_log(db_session, ta.id, student_a)

    foreign = await client.get(
        f"/api/v1/students/{student_a.id}/work-timeline",
        headers={"X-API-Key": key_b},
    )
    assert foreign.status_code == 404


@pytest.mark.asyncio
async def test_result_recorded_does_not_change_status_or_log_outcome(
    client, tenant_factory, db_session
):
    tenant, key = await tenant_factory(slug="w431-result")
    headers = {"X-API-Key": key}
    student = await _seed_student(db_session, tenant.id, "R1")
    log = await _seed_log(db_session, tenant.id, student, status="sent")
    log.outcome = None
    await db_session.commit()

    created = await client.post(
        "/api/v1/work/activities",
        headers=headers,
        json={
            "title": "Contato",
            "student_id": student.id,
            "intervention_log_id": log.id,
        },
    )
    aid = created.json()["id"]
    assert created.json()["status"] == "open"

    res = await client.post(
        f"/api/v1/work/activities/{aid}/result",
        headers=headers,
        json={"note": "Aluno não atendeu", "kind": "unreachable"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "open"
    types = [e["event_type"] for e in res.json()["events"]]
    assert "result_recorded" in types

    detail = await client.get(f"/api/v1/work/activities/{aid}", headers=headers)
    assert detail.json()["status"] == "open"

    await db_session.refresh(log)
    assert log.outcome is None
    assert log.status == "sent"


@pytest.mark.asyncio
async def test_unauthenticated_blocked(client):
    r = await client.get("/api/v1/work/activities")
    assert r.status_code == 401
    r2 = await client.get(f"/api/v1/students/{uuid4()}/work-timeline")
    assert r2.status_code == 401
