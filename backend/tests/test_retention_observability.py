"""Integration tests for closed-loop retention analytics and engagement events."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models.engagement import StudentEngagementEvent
from app.models.intervention import InterventionLog, ProviderCallMetric
from app.models.student import Student, UploadBatch
from app.models.tenant import TrainingEvent
from app.services.delivery_webhooks import apply_delivery_event, normalize_delivery_event
from app.services.engagement import is_sms_suppressed_by_recent_engagement


async def _make_student(session, tenant, matricula: str = "OBS-1"):
    batch = UploadBatch(
        filename="observability.csv",
        original_filename="observability.csv",
        status="scored",
        tenant_id=tenant.id,
    )
    session.add(batch)
    await session.flush()
    student = Student(
        batch_id=batch.id,
        tenant_id=tenant.id,
        matricula=matricula,
        nome="Aluno Observabilidade",
        curso="Engenharia",
        risk_level="critico",
        risk_score=82.0,
        telefone="11988887777",
        email="observability@example.com",
    )
    session.add(student)
    await session.commit()
    await session.refresh(student)
    return student


async def test_analytics_endpoint_returns_channel_delivery_attribution_cost_and_latency(
    client, auth_headers, tenant, db_session, monkeypatch
):
    from app.core.config import get_settings

    tenant_obj, _key = tenant
    student = await _make_student(db_session, tenant_obj)
    now = datetime.now(timezone.utc)
    log = InterventionLog(
        tenant_id=tenant_obj.id,
        student_id=student.id,
        matricula=student.matricula,
        channel="whatsapp",
        status="sent",
        delivery_status="clicked",
        external_id="wa-observability-1",
        outcome="stayed",
        outcome_at=now,
        outcome_source="import",
        created_at=now - timedelta(hours=2),
    )
    db_session.add(log)
    await db_session.flush()
    db_session.add(
        ProviderCallMetric(
            tenant_id=tenant_obj.id,
            intervention_log_id=log.id,
            channel="whatsapp",
            provider="waha",
            latency_ms=245.0,
            succeeded=True,
            provider_outcome="confirmed_success",
            occurred_at=now - timedelta(hours=2),
        )
    )
    await db_session.commit()
    monkeypatch.setattr(get_settings(), "agents_cost_per_whatsapp_message_brl", 0.25)

    response = await client.get(
        "/api/v1/agents/retention/analytics?days=30",
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["summary"]["messages_sent"] == 1
    assert body["summary"]["unique_students_contacted"] == 1
    assert body["summary"]["retained_students"] == 1
    assert body["summary"]["retention_rate_pct"] == 100.0
    assert body["summary"]["estimated_cost_brl_total"] == 0.25
    whatsapp = body["channels"]["whatsapp"]
    assert whatsapp["delivery_rate_pct"] == 100.0
    assert whatsapp["engagement_rate_pct"] == 100.0
    assert whatsapp["attribution"]["retained_students"] == 1
    assert whatsapp["average_latency_ms"] == 245.0
    assert body["providers"][0]["provider"] == "waha"
    assert body["providers"][0]["attempts"] == 1


async def test_click_webhook_records_engagement_event_and_suppresses_redundant_sms(
    tenant, db_session
):
    tenant_obj, _key = tenant
    student = await _make_student(db_session, tenant_obj, "OBS-CLICK")
    log = InterventionLog(
        tenant_id=tenant_obj.id,
        student_id=student.id,
        matricula=student.matricula,
        channel="email",
        status="sent",
        delivery_status="delivered",
        external_id="re-click-1",
    )
    db_session.add(log)
    await db_session.commit()

    event = normalize_delivery_event(
        "resend",
        {"type": "email.clicked", "data": {"email_id": "re-click-1"}},
    )
    assert event is not None and event.status == "clicked"
    result = await apply_delivery_event(db_session, tenant_id=tenant_obj.id, event=event)
    assert result["updated"] is True

    persisted = (
        await db_session.execute(
            select(StudentEngagementEvent).where(
                StudentEngagementEvent.tenant_id == tenant_obj.id,
                StudentEngagementEvent.student_id == student.id,
                StudentEngagementEvent.event_type == "clicked",
            )
        )
    ).scalar_one()
    assert persisted.intervention_log_id == log.id
    assert await is_sms_suppressed_by_recent_engagement(
        db_session, tenant_id=tenant_obj.id, student_id=student.id
    ) is True


async def test_imported_academic_outcome_is_attributed_to_prior_sent_intervention(
    client, auth_headers, tenant, db_session
):
    tenant_obj, _key = tenant
    student = await _make_student(db_session, tenant_obj, "OBS-ATTR")
    now = datetime.now(timezone.utc)
    training = TrainingEvent(
        tenant_id=tenant_obj.id,
        student_id=student.id,
        matricula=student.matricula,
        scored_at=now - timedelta(days=60),
        features_snapshot={
            "dias_atraso_boleto": 5,
            "recorrencia_atrasos": 1,
            "dias_sem_login": 8,
            "presenca_percentual": 85,
            "nota_media": 7,
            "reprovacoes": 0,
            "semestre": 2,
        },
    )
    log = InterventionLog(
        tenant_id=tenant_obj.id,
        student_id=student.id,
        matricula=student.matricula,
        channel="whatsapp",
        status="sent",
        delivery_status="delivered",
        created_at=now - timedelta(days=20),
    )
    db_session.add_all([training, log])
    await db_session.commit()

    response = await client.post(
        "/api/v1/outcomes",
        headers=auth_headers,
        json={
            "tenant_slug": tenant_obj.slug,
            "outcomes": [{
                "matricula": student.matricula,
                "training_event_id": training.id,
                "outcome": "ativo",
                "observed_at": (now - timedelta(days=1)).isoformat(),
            }],
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["attributed_interventions"] == 1
    await db_session.refresh(log)
    assert log.outcome == "stayed"
    assert log.outcome_source == "import"
