"""Smart CRM behavior properties, send-time optimization, and engagement-driven score tests."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.agents.base import MessageContext
from app.agents.templates import render_email_body, render_sms, render_whatsapp
from app.models.engagement import StudentEngagementEvent
from app.models.intervention import InterventionLog
from app.models.student import Student, UploadBatch
from app.services.engagement import (
    normalize_behavior_properties,
    recommend_send_time,
    record_engagement_event,
    refresh_engagement_profile,
    sweep_unanswered_reads,
)


async def _student(db_session, tenant, *, matricula="SMART-1", risk_score=68.0):
    batch = UploadBatch(
        filename="smart.csv",
        original_filename="smart.csv",
        status="scored",
        tenant_id=tenant.id,
        total_rows=1,
        processed_rows=1,
    )
    db_session.add(batch)
    await db_session.flush()
    student = Student(
        batch_id=batch.id,
        tenant_id=tenant.id,
        matricula=matricula,
        nome="Ana da Silva",
        curso="Engenharia",
        telefone="11988887777",
        email="ana@example.edu.br",
        risk_level="medio" if risk_score < 70 else "critico",
        risk_score=risk_score,
        model_risk_score=risk_score,
        dynamic_risk_adjustment=0.0,
        behavior_properties={},
        communication_preferences={
            "channels": {"whatsapp": True, "email": True, "sms": True},
            "topics": {"academic": True, "retention": True, "promotional": False},
        },
    )
    db_session.add(student)
    await db_session.commit()
    await db_session.refresh(student)
    return student


def test_behavior_properties_are_validated_and_only_selected_fields_are_rendered():
    properties = normalize_behavior_properties(
        {},
        {
            "last_class_missed": "Cálculo II",
            "missed_classes_this_week": 2,
            "current_module": "Módulo 4",
            "module_progress_pct": 45,
            "custom_properties": {"tutor_responsavel": "Prof. Almeida", "turno": "Noturno"},
            "message_fields": [
                "last_class_missed",
                "current_module",
                "module_progress_pct",
                "custom_properties.tutor_responsavel",
            ],
        },
    )
    ctx = MessageContext(
        tenant_id="tenant",
        student_id="student",
        matricula="RA-1",
        nome="Ana da Silva",
        curso="Engenharia",
        risk_level="critico",
        behavior_properties=properties,
    )
    whatsapp = render_whatsapp(ctx)
    email = render_email_body(ctx)
    assert "aula de Cálculo II" in whatsapp
    assert "Módulo 4 está em 45%" in email
    assert "tutor responsável: Prof. Almeida" in email
    assert "Noturno" not in email
    assert "2 falta(s)" not in email  # The tenant did not opt in that property.
    sms = render_sms(ctx)
    assert len(sms) <= 160


def test_behavior_property_validation_rejects_bad_ranges_and_unknown_fields():
    with pytest.raises(ValueError, match="entre 0 e 100"):
        normalize_behavior_properties({}, {"module_progress_pct": 140})
    with pytest.raises(ValueError, match="não suportadas"):
        normalize_behavior_properties({}, {"unsafe_raw_message": "send arbitrary content"})
    with pytest.raises(ValueError, match="message_fields"):
        normalize_behavior_properties({}, {"message_fields": ["custom_properties.password"]})


@pytest.mark.asyncio
async def test_behavior_properties_endpoint_is_tenant_scoped_and_persists_opt_in_fields(
    client, tenant, tenant_factory, db_session
):
    tenant_obj, key = tenant
    _other, other_key = await tenant_factory(slug="smart-other")
    student = await _student(db_session, tenant_obj)
    url = f"/api/v1/students/{student.id}/behavior-properties"
    response = await client.patch(
        url,
        headers={"X-API-Key": key},
        json={
            "properties": {
                "last_class_missed": "Cálculo II",
                "module_progress_pct": 45,
                "custom_properties": {"tutor_responsavel": "Prof. Almeida"},
                "message_fields": ["last_class_missed", "module_progress_pct", "custom_properties.tutor_responsavel"],
            }
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["properties"]["module_progress_pct"] == 45
    assert body["message_fields"][-1] == "custom_properties.tutor_responsavel"

    loaded = await client.get(url, headers={"X-API-Key": key})
    assert loaded.status_code == 200
    assert loaded.json()["properties"]["last_class_missed"] == "Cálculo II"
    denied = await client.get(url, headers={"X-API-Key": other_key})
    assert denied.status_code == 404


@pytest.mark.asyncio
async def test_engagement_updates_index_and_risk_with_bounded_unanswered_adjustment(tenant, db_session):
    tenant_obj, _key = tenant
    student = await _student(db_session, tenant_obj, risk_score=68)
    log = InterventionLog(
        tenant_id=tenant_obj.id,
        student_id=student.id,
        matricula=student.matricula,
        channel="whatsapp",
        risk_level="medio",
        risk_score=68,
        status="sent",
        delivery_status="read",
        created_at=datetime.now(timezone.utc) - timedelta(days=4),
        delivery_updated_at=datetime.now(timezone.utc) - timedelta(days=4),
    )
    db_session.add(log)
    await db_session.commit()

    negative = await record_engagement_event(
        db_session,
        tenant_id=tenant_obj.id,
        student_id=student.id,
        event_key=f"test-no-response:{log.id}",
        event_type="no_response",
        channel="whatsapp",
        source="test",
        intervention_log_id=log.id,
        occurred_at=datetime.now(timezone.utc),
    )
    assert negative["created"] is True
    await db_session.refresh(student)
    assert student.dynamic_risk_adjustment == 5
    assert student.risk_score == 73
    assert student.risk_level == "critico"
    assert student.engagement_score is not None
    assert student.engagement_score_updated_at is not None

    positive = await record_engagement_event(
        db_session,
        tenant_id=tenant_obj.id,
        student_id=student.id,
        event_key=f"test-replied:{log.id}",
        event_type="replied",
        channel="whatsapp",
        source="operator",
        intervention_log_id=log.id,
        occurred_at=datetime.now(timezone.utc),
    )
    assert positive["created"] is True
    await db_session.refresh(student)
    assert student.dynamic_risk_adjustment == 0
    assert student.risk_score == 68
    assert student.risk_level == "medio"


@pytest.mark.asyncio
async def test_send_time_recommendation_uses_send_hour_not_event_hour(tenant, db_session):
    tenant_obj, _key = tenant
    student = await _student(db_session, tenant_obj, risk_score=82)
    now = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)  # 09:00 in Sao Paulo.
    for index, day in enumerate((20, 21, 22), start=1):
        sent_at = datetime(2026, 10, day, 13, 15, tzinfo=timezone.utc)  # 10:15 local
        log = InterventionLog(
            tenant_id=tenant_obj.id,
            student_id=student.id,
            matricula=student.matricula,
            channel="email",
            risk_level="critico",
            risk_score=82,
            status="sent",
            delivery_status="submitted",
            created_at=sent_at,
        )
        db_session.add(log)
        await db_session.flush()
        db_session.add(
            StudentEngagementEvent(
                tenant_id=tenant_obj.id,
                student_id=student.id,
                intervention_log_id=log.id,
                event_key=f"read:{student.id}:{index}",
                event_type="read",
                channel="email",
                source="test",
                occurred_at=sent_at + timedelta(minutes=35),
            )
        )
    await db_session.commit()

    recommendation = await recommend_send_time(
        db_session,
        tenant_id=tenant_obj.id,
        student_id=student.id,
        channels=["email"],
        now=now,
    )
    assert recommendation["channel"] == "email"
    assert recommendation["preferred_hour_local"] == 10
    assert recommendation["confidence"] == "medium"
    assert recommendation["historical_attempts_at_hour"] == 3
    assert recommendation["next_send_at"] == "2026-10-23T13:00:00+00:00"


@pytest.mark.asyncio
async def test_unanswered_read_sweep_has_safe_preview_then_updates_engagement_risk(tenant, db_session):
    tenant_obj, _key = tenant
    student = await _student(db_session, tenant_obj, risk_score=60)
    now = datetime.now(timezone.utc)
    log = InterventionLog(
        tenant_id=tenant_obj.id,
        student_id=student.id,
        matricula=student.matricula,
        channel="whatsapp",
        risk_level="medio",
        risk_score=60,
        status="sent",
        delivery_status="read",
        created_at=now - timedelta(days=5),
        delivery_updated_at=now - timedelta(days=5),
    )
    db_session.add(log)
    await db_session.commit()

    preview = await sweep_unanswered_reads(
        db_session, now=now, response_window_hours=72, dry_run=True
    )
    assert preview["candidates"] == 1
    assert preview["events_created"] == 0

    applied = await sweep_unanswered_reads(
        db_session, now=now, response_window_hours=72, dry_run=False
    )
    assert applied["events_created"] == 1
    await db_session.refresh(student)
    assert student.dynamic_risk_adjustment == 5
    assert student.risk_score == 65

    again = await sweep_unanswered_reads(
        db_session, now=now, response_window_hours=72, dry_run=False
    )
    assert again["events_created"] == 0
    count = (
        await db_session.execute(
            select(StudentEngagementEvent.id).where(
                StudentEngagementEvent.tenant_id == tenant_obj.id,
                StudentEngagementEvent.event_type == "no_response",
                StudentEngagementEvent.intervention_log_id == log.id,
            )
        )
    ).scalars().all()
    assert len(count) == 1


@pytest.mark.asyncio
async def test_enqueue_send_time_optimization_schedules_each_student_separately(
    client, tenant, db_session, monkeypatch
):
    tenant_obj, key = tenant
    student = await _student(db_session, tenant_obj, risk_score=85)
    from app.api import agents as agents_api

    scheduled = []

    async def fake_recommend(_session, *, tenant_id, student_id, channels):
        assert tenant_id == tenant_obj.id
        assert student_id == student.id
        assert channels
        return {
            "student_id": student_id,
            "channel": "whatsapp",
            "preferred_hour_local": 10,
            "timezone": "America/Sao_Paulo",
            "next_send_at": "2026-10-25T13:00:00+00:00",
            "confidence": "fallback",
            "reason": "insufficient_history_default_10am",
            "historical_attempts_at_hour": 0,
            "engagement_rate_pct_at_hour": None,
            "history_days": 90,
        }

    async def fake_enqueue(**kwargs):
        scheduled.append(kwargs)
        return {"id": "queued-smart-1", "status": "scheduled", "created_at": 123.0}

    monkeypatch.setattr(agents_api, "recommend_send_time", fake_recommend)
    monkeypatch.setattr(agents_api, "enqueue_retention_job", fake_enqueue)

    response = await client.post(
        "/api/v1/agents/retention/enqueue",
        headers={"X-API-Key": key, "Idempotency-Key": "smart-crm-test"},
        json={
            "risk_levels": ["critico"],
            "limit": 10,
            "dry_run": True,
            "optimize_send_time": True,
        },
    )
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["scheduled_count"] == 1
    assert body["scheduled_jobs"][0]["student_id"] == student.id
    assert body["scheduled_jobs"][0]["channel"] == "whatsapp"
    assert body["scheduled_jobs"][0]["status"] == "scheduled"
    assert len(scheduled) == 1
    assert scheduled[0]["payload"]["student_ids"] == [student.id]
    assert scheduled[0]["scheduled_at"].isoformat() == "2026-10-25T13:00:00+00:00"
