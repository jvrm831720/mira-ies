"""Testes de integracao do orquestrador de retencao e da API de agentes."""
from app.models.student import Student, UploadBatch


async def _create_student(db_session, tenant, **overrides):
    batch = UploadBatch(filename="x.csv", original_filename="x.csv", status="scored", tenant_id=tenant.id)
    db_session.add(batch)
    await db_session.flush()
    defaults = dict(
        batch_id=batch.id, tenant_id=tenant.id, matricula="S1", nome="Fulano de Tal",
        curso="Engenharia", risk_level="critico", risk_score=85.0,
        telefone="11988887777", email="fulano@example.com",
        shap_top_factors={"recommended_actions": ["Agendar atendimento"], "top_3": [{"label": "Atraso financeiro"}]},
    )
    defaults.update(overrides)
    student = Student(**defaults)
    db_session.add(student)
    await db_session.commit()
    await db_session.refresh(student)
    return student


async def test_orchestrator_dry_run_creates_dry_run_log(tenant, db_session):
    t, _raw_key = tenant
    await _create_student(db_session, t)

    from app.agents.orchestrator import RetentionOrchestrator
    orch = RetentionOrchestrator(db_session, tenant_id=t.id)
    result = await orch.run(risk_levels=["critico"], dry_run=True)

    assert result["totals"]["dry_run"] == 1
    assert result["by_channel"]["whatsapp"]["dry_run"] == 1

    from sqlalchemy import select
    from app.models.intervention import InterventionLog
    logs = (await db_session.execute(select(InterventionLog).where(InterventionLog.tenant_id == t.id))).scalars().all()
    assert len(logs) == 1
    assert logs[0].status == "dry_run"
    assert logs[0].channel == "whatsapp"
    assert logs[0].message_preview


async def test_orchestrator_anti_spam_blocks_second_contact_same_channel_within_48h(tenant, db_session):
    t, _raw_key = tenant
    await _create_student(db_session, t)

    from app.agents.orchestrator import RetentionOrchestrator
    orch = RetentionOrchestrator(db_session, tenant_id=t.id)
    first = await orch.run(risk_levels=["critico"], dry_run=True, channels=["whatsapp"])
    assert first["totals"]["dry_run"] == 1

    second = await orch.run(risk_levels=["critico"], dry_run=True, channels=["whatsapp"])
    assert second["totals"]["dry_run"] == 0
    assert second["totals"]["skipped"] == 1
    assert second["by_channel"]["whatsapp"]["skipped"] == 1


async def test_orchestrator_falls_back_to_email_when_whatsapp_already_contacted(tenant, db_session):
    t, _raw_key = tenant
    await _create_student(db_session, t)

    from app.agents.orchestrator import RetentionOrchestrator
    orch = RetentionOrchestrator(db_session, tenant_id=t.id)
    await orch.run(risk_levels=["critico"], dry_run=True, channels=["whatsapp"])

    second = await orch.run(risk_levels=["critico"], dry_run=True)
    assert second["by_channel"]["whatsapp"]["skipped"] == 1
    assert second["by_channel"]["email"]["dry_run"] == 1


async def test_orchestrator_skips_student_without_contact_info(tenant, db_session):
    t, _raw_key = tenant
    await _create_student(db_session, t, telefone=None, email=None)

    from app.agents.orchestrator import RetentionOrchestrator
    orch = RetentionOrchestrator(db_session, tenant_id=t.id)
    result = await orch.run(risk_levels=["critico"], dry_run=True)
    assert result["totals"]["skipped"] == 1
    assert result["by_channel"]["_none"]["skipped"] == 1


async def test_orchestrator_skips_opted_out_student_and_logs_reason(tenant, db_session):
    t, _raw_key = tenant
    await _create_student(db_session, t, communication_opt_out=True)

    from app.agents.orchestrator import RetentionOrchestrator
    orch = RetentionOrchestrator(db_session, tenant_id=t.id)
    result = await orch.run(risk_levels=["critico"], dry_run=True)
    assert result["totals"] == {"sent": 0, "dry_run": 0, "skipped": 1, "failed": 0}

    from sqlalchemy import select
    from app.models.intervention import InterventionLog
    log = (await db_session.execute(select(InterventionLog))).scalar_one()
    assert log.skip_reason == "communication_opt_out"
    assert log.channel is None


async def test_orchestrator_does_not_fire_for_baixo_risk(tenant, db_session):
    t, _raw_key = tenant
    await _create_student(db_session, t, risk_level="baixo")

    from app.agents.orchestrator import RetentionOrchestrator
    orch = RetentionOrchestrator(db_session, tenant_id=t.id)
    result = await orch.run(risk_levels=["baixo"], dry_run=True)
    assert result["totals"] == {"sent": 0, "dry_run": 0, "skipped": 1, "failed": 0}


async def test_orchestrator_never_contacts_other_tenant_students(tenant_factory, db_session):
    t_a, _ka = await tenant_factory(slug="agent-a", name="Agent A")
    t_b, _kb = await tenant_factory(slug="agent-b", name="Agent B")
    await _create_student(db_session, t_a)

    from app.agents.orchestrator import RetentionOrchestrator
    orch_b = RetentionOrchestrator(db_session, tenant_id=t_b.id)
    result = await orch_b.run(risk_levels=["critico"], dry_run=True)
    assert result["students_evaluated"] == 0


async def test_preview_does_not_write_log(tenant, db_session):
    t, _raw_key = tenant
    student = await _create_student(db_session, t)

    from app.agents.orchestrator import preview_message
    result = await preview_message(db_session, tenant_id=t.id, student_id=student.id)
    assert result["channel"] == "whatsapp"
    assert result["message"]

    from sqlalchemy import select, func
    from app.models.intervention import InterventionLog
    count = (await db_session.execute(
        select(func.count(InterventionLog.id)).where(InterventionLog.tenant_id == t.id)
    )).scalar()
    assert count == 0


async def test_preview_reports_missing_contact(tenant, db_session):
    t, _raw_key = tenant
    student = await _create_student(db_session, t, telefone=None, email=None)

    from app.agents.orchestrator import preview_message
    result = await preview_message(db_session, tenant_id=t.id, student_id=student.id)
    assert result["channel"] is None
    assert result["reason"] == "missing_contact"


async def test_preview_does_not_render_message_for_opted_out_student(tenant, db_session):
    t, _raw_key = tenant
    student = await _create_student(db_session, t, communication_opt_out=True)

    from app.agents.orchestrator import preview_message
    result = await preview_message(db_session, tenant_id=t.id, student_id=student.id)
    assert result["channel"] is None
    assert result["message"] is None
    assert result["reason"] == "communication_opt_out"


async def test_run_endpoint_requires_auth(client):
    resp = await client.post("/api/v1/agents/retention/run", json={"risk_levels": ["critico"]})
    assert resp.status_code == 401


async def test_run_endpoint_rejects_invalid_risk_level(client, auth_headers):
    resp = await client.post(
        "/api/v1/agents/retention/run", headers=auth_headers, json={"risk_levels": ["urgentissimo"]},
    )
    assert resp.status_code == 422


async def test_run_endpoint_dry_run_via_api(client, auth_headers, tenant, db_session):
    t, _raw_key = tenant
    await _create_student(db_session, t)
    resp = await client.post(
        "/api/v1/agents/retention/run", headers=auth_headers,
        json={"risk_levels": ["critico"], "dry_run": True},
    )
    assert resp.status_code == 200
    assert resp.json()["totals"]["dry_run"] == 1

    resp_logs = await client.get("/api/v1/agents/retention/logs", headers=auth_headers)
    assert resp_logs.status_code == 200
    assert resp_logs.json()["count"] == 1


async def test_preview_endpoint_requires_auth(client, tenant, db_session):
    t, _raw_key = tenant
    student = await _create_student(db_session, t)
    resp = await client.get(f"/api/v1/agents/retention/preview/{student.id}")
    assert resp.status_code == 401


async def test_communication_preference_endpoint_updates_opt_out(client, auth_headers, tenant, db_session):
    t, _raw_key = tenant
    student = await _create_student(db_session, t)
    resp = await client.patch(
        f"/api/v1/students/{student.id}/communication-preferences",
        headers=auth_headers,
        json={"opt_out": True},
    )
    assert resp.status_code == 200
    assert resp.json()["communication_opt_out"] is True
    await db_session.refresh(student)
    assert student.communication_opt_out is True
    assert student.communication_opted_out_at is not None


async def test_preview_endpoint_404_for_other_tenant_student(client, tenant_factory, db_session):
    t_a, _ka = await tenant_factory(slug="prev-a", name="Prev A")
    _t_b, kb = await tenant_factory(slug="prev-b", name="Prev B")
    student = await _create_student(db_session, t_a)

    resp = await client.get(f"/api/v1/agents/retention/preview/{student.id}", headers={"X-API-Key": kb})
    assert resp.status_code == 404


async def test_agents_status_endpoint_defaults_to_dry_run(client, auth_headers):
    resp = await client.get("/api/v1/agents/status", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["providers"] == {"whatsapp": "dry_run", "email": "dry_run", "sms": "dry_run"}
    assert body["dry_run_default"] is True
