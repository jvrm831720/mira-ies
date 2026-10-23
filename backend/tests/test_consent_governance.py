"""Integration/regression coverage for consent governance and raw-log TTL."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.models.consent import ConsentAuditEvent
from app.models.intervention import InterventionLog, InterventionLogDailyAggregate
from app.models.student import Student, UploadBatch
from app.services.consent import effective_preferences
from app.services.delivery_webhooks import apply_delivery_event, normalize_delivery_event
from app.services.intervention_log_retention import purge_expired_intervention_logs


async def _create_student(db_session, tenant, *, matricula="CONSENT-1", prefs=None):
    batch = UploadBatch(
        filename="consent.csv",
        original_filename="consent.csv",
        status="processed",
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
        nome="Aluno de Teste",
        telefone="11988887777",
        email="aluno@example.edu.br",
        risk_level="critico",
        risk_score=91.0,
        communication_preferences=prefs or {
            "channels": {"whatsapp": True, "email": True, "sms": True},
            "topics": {"academic": True, "retention": True, "promotional": False},
        },
    )
    db_session.add(student)
    await db_session.commit()
    await db_session.refresh(student)
    return student


@pytest.mark.asyncio
async def test_preferences_are_granular_and_audited_per_change(client, tenant, db_session):
    tenant_obj, key = tenant
    student = await _create_student(db_session, tenant_obj)
    headers = {"X-API-Key": key}

    initial = await client.get(
        f"/api/v1/students/{student.id}/communication-preferences", headers=headers
    )
    assert initial.status_code == 200
    assert initial.json()["channels"] == {"whatsapp": True, "email": True, "sms": True}
    assert initial.json()["topics"]["promotional"] is False

    updated = await client.patch(
        f"/api/v1/students/{student.id}/communication-preferences",
        headers=headers,
        json={"channels": {"sms": False}, "topics": {"promotional": True}},
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["channels"]["sms"] is False
    assert body["channels"]["email"] is True
    assert body["topics"]["promotional"] is True
    assert body["opt_out"] is False
    assert body["audit_events_created"] == 2

    audit = await client.get(
        f"/api/v1/students/{student.id}/consent-audit?limit=20", headers=headers
    )
    assert audit.status_code == 200
    events = audit.json()["events"]
    assert len(events) == 2
    assert {event["event_type"] for event in events} == {
        "channel_preference_changed",
        "topic_preference_changed",
    }
    assert all(event["source"] == "authenticated_api" for event in events)
    assert all(event["method"] == "manual_preferences_update" for event in events)
    assert all(event["location"] == "student_profile_preferences" for event in events)
    assert all(event["occurred_at"] for event in events)


@pytest.mark.asyncio
async def test_preference_and_audit_endpoints_are_tenant_scoped(client, tenant_factory, db_session):
    tenant_a, key_a = await tenant_factory(slug="consent-owner")
    _tenant_b, key_b = await tenant_factory(slug="consent-outsider")
    student = await _create_student(db_session, tenant_a)
    url = f"/api/v1/students/{student.id}/communication-preferences"
    audit_url = f"/api/v1/students/{student.id}/consent-audit"

    response = await client.patch(
        url,
        headers={"X-API-Key": key_a},
        json={"channels": {"sms": False}},
    )
    assert response.status_code == 200

    denied = await client.get(url, headers={"X-API-Key": key_b})
    denied_audit = await client.get(audit_url, headers={"X-API-Key": key_b})
    assert denied.status_code == 404
    assert denied_audit.status_code == 404

    owner_audit = await client.get(audit_url, headers={"X-API-Key": key_a})
    assert owner_audit.status_code == 200
    assert owner_audit.json()["count"] == 1


@pytest.mark.asyncio
async def test_opt_out_column_from_upload_is_recorded_in_consent_trail(client, tenant, db_session):
    tenant_obj, key = tenant
    csv = (
        b"matricula,nome,communication_opt_out\n"
        b"CSV-OPT-1,Aluno Optout,true\n"
    )
    response = await client.post(
        "/api/v1/upload",
        headers={"X-API-Key": key},
        files={"file": ("opt-out.csv", csv, "text/csv")},
        params={"auto_score": "false"},
    )
    assert response.status_code == 201, response.text

    student = (
        await db_session.execute(
            select(Student).where(
                Student.tenant_id == tenant_obj.id,
                Student.matricula == "CSV-OPT-1",
            )
        )
    ).scalar_one()
    event = (
        await db_session.execute(
            select(ConsentAuditEvent).where(
                ConsentAuditEvent.tenant_id == tenant_obj.id,
                ConsentAuditEvent.student_id == student.id,
            )
        )
    ).scalar_one()
    assert student.communication_opt_out is True
    assert event.event_type == "global_opt_out_enabled"
    assert event.source == "csv_upload"
    assert event.method == "import_column"
    assert event.location == "student_import"
    assert event.source_reference == response.json()["batch"]["id"]


@pytest.mark.asyncio
async def test_provider_unsubscribe_disables_only_the_identified_channel(tenant, db_session):
    tenant_obj, _key = tenant
    student = await _create_student(db_session, tenant_obj)
    log = InterventionLog(
        tenant_id=tenant_obj.id,
        student_id=student.id,
        matricula=student.matricula,
        channel="sms",
        risk_level="critico",
        status="sent",
        external_id="SM-CONSENT-1",
        delivery_status="submitted",
    )
    db_session.add(log)
    await db_session.commit()

    event = normalize_delivery_event("twilio", {"MessageSid": "SM-CONSENT-1", "Body": "STOP"})
    assert event and event.status == "opted_out"
    result = await apply_delivery_event(db_session, tenant_id=tenant_obj.id, event=event)
    assert result["updated"] is True

    await db_session.refresh(student)
    effective = effective_preferences(student)
    assert student.communication_opt_out is False
    assert effective["channels"]["sms"] is False
    assert effective["channels"]["email"] is True
    assert effective["channels"]["whatsapp"] is True

    audit = (
        await db_session.execute(
            select(ConsentAuditEvent).where(
                ConsentAuditEvent.tenant_id == tenant_obj.id,
                ConsentAuditEvent.student_id == student.id,
            )
        )
    ).scalar_one()
    assert audit.source == "provider_webhook"
    assert audit.method == "unsubscribe_event"
    assert audit.location == "provider:twilio"
    assert audit.source_reference == event.event_id
    assert audit.channel == "sms"
    assert audit.new_value is False


@pytest.mark.asyncio
async def test_retention_orchestrator_skips_disallowed_channels_but_uses_allowed_fallback(
    tenant, db_session, monkeypatch
):
    tenant_obj, _key = tenant
    student = await _create_student(
        db_session,
        tenant_obj,
        prefs={
            "channels": {"whatsapp": False, "email": True, "sms": True},
            "topics": {"academic": True, "retention": True, "promotional": False},
        },
    )
    from app.agents import orchestrator as orchestrator_module

    settings = orchestrator_module.get_settings()
    monkeypatch.setattr(settings, "agents_min_hours_between_contact", -1)
    monkeypatch.setattr(settings, "agents_max_contacts_per_week", 10)

    result = await orchestrator_module.RetentionOrchestrator(
        db_session, tenant_id=tenant_obj.id
    ).run(risk_levels=["critico"], dry_run=True)

    assert result["totals"]["dry_run"] == 1
    assert result["by_channel"]["email"]["dry_run"] == 1
    logs = (
        await db_session.execute(
            select(InterventionLog).where(InterventionLog.student_id == student.id)
        )
    ).scalars().all()
    assert len(logs) == 1
    assert logs[0].channel == "email"


@pytest.mark.asyncio
async def test_purge_aggregates_expired_logs_without_retaining_student_identifiers(tenant, db_session):
    tenant_obj, _key = tenant
    student = await _create_student(db_session, tenant_obj)
    now = datetime.now(timezone.utc)
    old_log = InterventionLog(
        tenant_id=tenant_obj.id,
        student_id=student.id,
        matricula=student.matricula,
        channel="email",
        risk_level="critico",
        status="sent",
        outcome="responded",
        created_at=now - timedelta(days=220),
    )
    recent_log = InterventionLog(
        tenant_id=tenant_obj.id,
        student_id=student.id,
        matricula=student.matricula,
        channel="sms",
        risk_level="medio",
        status="dry_run",
        created_at=now - timedelta(days=2),
    )
    db_session.add_all([old_log, recent_log])
    await db_session.commit()

    preview = await purge_expired_intervention_logs(
        db_session, now=now, retention_days=180, dry_run=True
    )
    assert preview["expired_logs"] == 1
    assert preview["aggregate_buckets"] == 1
    assert preview["deleted_logs"] == 0
    assert (await db_session.execute(select(func.count(InterventionLog.id)))).scalar_one() == 2

    applied = await purge_expired_intervention_logs(
        db_session, now=now, retention_days=180, dry_run=False
    )
    assert applied["deleted_logs"] == 1
    logs = (await db_session.execute(select(InterventionLog))).scalars().all()
    assert len(logs) == 1 and logs[0].status == "dry_run"

    aggregate = (
        await db_session.execute(select(InterventionLogDailyAggregate))
    ).scalar_one()
    assert aggregate.tenant_id == tenant_obj.id
    assert aggregate.event_count == 1
    assert aggregate.status == "sent"
    assert aggregate.channel_bucket == "email"
    assert aggregate.risk_level_bucket == "critico"
    assert aggregate.outcome_bucket == "responded"
    assert not hasattr(aggregate, "student_id")
    assert not hasattr(aggregate, "matricula")

    # Repetir o expurgo é idempotente: não há logs vencidos nem contagem duplicada.
    second = await purge_expired_intervention_logs(
        db_session, now=now, retention_days=180, dry_run=False
    )
    assert second["deleted_logs"] == 0
    await db_session.refresh(aggregate)
    assert aggregate.event_count == 1

@pytest.mark.asyncio
async def test_retention_period_must_stay_within_the_governed_range(db_session):
    with pytest.raises(ValueError, match="entre 90 e 180"):
        await purge_expired_intervention_logs(db_session, retention_days=89, dry_run=True)
    with pytest.raises(ValueError, match="entre 90 e 180"):
        await purge_expired_intervention_logs(db_session, retention_days=181, dry_run=True)
