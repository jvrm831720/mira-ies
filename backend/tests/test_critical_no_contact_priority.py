"""Verifiable 7-day critical-student contact priority; no outreach side effects."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.api.work_activities import critical_students_without_recent_contact
from app.models.intervention import InterventionLog
from app.models.student import Student, UploadBatch
from app.models.work_activity import WorkActivity, WorkActivityEvent


@pytest.mark.asyncio
async def test_critical_no_contact_count_uses_evidence_and_tenant_scope(db_session, tenant_factory):
    tenant_a, _ = await tenant_factory(slug="priority-seven-a")
    tenant_b, _ = await tenant_factory(slug="priority-seven-b")
    now = datetime.now(timezone.utc)
    ids = {}
    for tenant, suffixes in (
        (tenant_a, ["fresh", "sent", "sending", "dry_run", "human_done", "human_unknown", "old"]),
        (tenant_b, ["foreign"]),
    ):
        batch = UploadBatch(tenant_id=tenant.id, filename="priority.csv", original_filename="priority.csv")
        db_session.add(batch)
        await db_session.flush()
        for suffix in suffixes:
            student = Student(
                batch_id=batch.id, tenant_id=tenant.id, matricula=f"{suffix}-{uuid4()}",
                nome=suffix, risk_level="critico", risk_score=90.0, is_active=True,
            )
            db_session.add(student)
            await db_session.flush()
            if tenant.id == tenant_a.id:
                ids[suffix] = student.id
    await db_session.commit()

    for suffix, status, days in (
        ("sent", "sent", 1),
        ("sending", "sending", 2),
        ("dry_run", "dry_run", 1),
        ("old", "sent", 8),
    ):
        db_session.add(InterventionLog(
            tenant_id=tenant_a.id, student_id=ids[suffix], matricula=suffix,
            status=status, channel="email", created_at=now - timedelta(days=days),
        ))
    success = WorkActivity(
        tenant_id=tenant_a.id, student_id=ids["human_done"],
        activity_type="contact", title="Contato positivo", status="completed",
        completed_at=now - timedelta(days=1),
    )
    unverified = WorkActivity(
        tenant_id=tenant_a.id, student_id=ids["human_unknown"],
        activity_type="contact", title="Concluída, resultado desconhecido",
        status="completed", completed_at=now - timedelta(days=1),
    )
    db_session.add_all([success, unverified])
    await db_session.flush()
    db_session.add(WorkActivityEvent(
        tenant_id=tenant_a.id, activity_id=success.id,
        event_type="result_recorded", payload={"kind": "done", "note": "Falou com aluno"},
        created_at=now - timedelta(days=1),
    ))
    await db_session.commit()

    result = await critical_students_without_recent_contact(
        auth=SimpleNamespace(tenant_id=tenant_a.id), db=db_session,
    )
    assert result["window_days"] == 7
    assert result["critical_total"] == 7
    assert result["contacted_7d"] == 2
    assert result["pending_verification"] == 2
    assert result["without_contact_7d"] == 3
    assert {s["id"] for s in result["candidates"]} == {ids[k] for k in ("fresh", "dry_run", "old")}
    assert result["critical_total"] == result["contacted_7d"] + result["pending_verification"] + result["without_contact_7d"]

    foreign = await critical_students_without_recent_contact(
        auth=SimpleNamespace(tenant_id=tenant_b.id), db=db_session,
    )
    assert foreign["critical_total"] == 1
    assert foreign["without_contact_7d"] == 1
    assert all(item["id"] not in ids.values() for item in foreign["candidates"])
