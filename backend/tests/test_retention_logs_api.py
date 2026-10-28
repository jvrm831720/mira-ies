"""API tests for GET /agents/retention/logs and work-summary."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models.intervention import InterventionLog
from app.models.student import Student, UploadBatch


async def _student(session, tenant, matricula: str = "LOG-1"):
    batch = UploadBatch(
        filename="logs.csv",
        original_filename="logs.csv",
        status="scored",
        tenant_id=tenant.id,
    )
    session.add(batch)
    await session.flush()
    student = Student(
        batch_id=batch.id,
        tenant_id=tenant.id,
        matricula=matricula,
        nome="Aluno Logs",
        curso="Direito",
        risk_level="critico",
        risk_score=90.0,
    )
    session.add(student)
    await session.commit()
    await session.refresh(student)
    return student


async def test_list_logs_empty_tenant(client, auth_headers):
    response = await client.get("/api/v1/agents/retention/logs?limit=10", headers=auth_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["count"] == 0
    assert body["logs"] == []


async def test_list_logs_status_planned_and_limit(client, auth_headers, tenant, db_session):
    tenant_obj, _key = tenant
    student = await _student(db_session, tenant_obj)
    now = datetime.now(timezone.utc)
    db_session.add_all(
        [
            InterventionLog(
                tenant_id=tenant_obj.id,
                student_id=student.id,
                matricula=student.matricula,
                channel="whatsapp",
                status="planned",
                risk_level="critico",
                risk_score=90.0,
                created_at=now - timedelta(hours=1),
            ),
            InterventionLog(
                tenant_id=tenant_obj.id,
                student_id=student.id,
                matricula=student.matricula,
                channel="email",
                status="sent",
                created_at=now - timedelta(hours=2),
            ),
        ]
    )
    await db_session.commit()

    planned = await client.get(
        "/api/v1/agents/retention/logs?limit=10&status=planned",
        headers=auth_headers,
    )
    assert planned.status_code == 200, planned.text
    body = planned.json()
    assert body["count"] == 1
    assert body["logs"][0]["status"] == "planned"
    assert body["logs"][0]["channel"] == "whatsapp"
    assert body["logs"][0]["matricula"] == student.matricula

    limited = await client.get(
        "/api/v1/agents/retention/logs?limit=1",
        headers=auth_headers,
    )
    assert limited.status_code == 200
    assert limited.json()["count"] == 1


async def test_work_summary_matches_planned_counts(client, auth_headers, tenant, db_session):
    tenant_obj, _key = tenant
    student = await _student(db_session, tenant_obj, "LOG-SUM")
    now = datetime.now(timezone.utc)
    db_session.add(
        InterventionLog(
            tenant_id=tenant_obj.id,
            student_id=student.id,
            matricula=student.matricula,
            channel="sms",
            status="planned",
            created_at=now - timedelta(hours=60),
        )
    )
    await db_session.commit()

    response = await client.get("/api/v1/agents/retention/work-summary", headers=auth_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["pending"] >= 1
    assert body["overdue_48h"] >= 1
    assert body["overdue_policy_hours"] == 48
    assert "definition" in body


async def test_logs_are_tenant_isolated(client, auth_headers, tenant, tenant_factory, db_session):
    tenant_a, _key_a = tenant
    tenant_b, key_b = await tenant_factory(slug="other-ies", name="Other IES")
    student_a = await _student(db_session, tenant_a, "ISO-A")
    student_b = await _student(db_session, tenant_b, "ISO-B")
    now = datetime.now(timezone.utc)
    db_session.add_all(
        [
            InterventionLog(
                tenant_id=tenant_a.id,
                student_id=student_a.id,
                matricula=student_a.matricula,
                channel="whatsapp",
                status="planned",
                created_at=now,
            ),
            InterventionLog(
                tenant_id=tenant_b.id,
                student_id=student_b.id,
                matricula=student_b.matricula,
                channel="email",
                status="planned",
                created_at=now,
            ),
        ]
    )
    await db_session.commit()

    resp_a = await client.get(
        "/api/v1/agents/retention/logs?status=planned",
        headers=auth_headers,
    )
    assert resp_a.status_code == 200
    mats_a = {row["matricula"] for row in resp_a.json()["logs"]}
    assert "ISO-A" in mats_a
    assert "ISO-B" not in mats_a

    resp_b = await client.get(
        "/api/v1/agents/retention/logs?status=planned",
        headers={"X-API-Key": key_b},
    )
    assert resp_b.status_code == 200
    mats_b = {row["matricula"] for row in resp_b.json()["logs"]}
    assert "ISO-B" in mats_b
    assert "ISO-A" not in mats_b
