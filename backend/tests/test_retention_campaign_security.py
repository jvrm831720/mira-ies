"""Security regression tests for retention campaigns."""
from __future__ import annotations

import pytest
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from app.models.retention_campaign import RetentionCampaign
from app.models.student import Student, UploadBatch


def _campaign_payload(slug: str, *, name: str = "Campanha de segurança") -> dict:
    return {
        "slug": slug,
        "name": name,
        "description": "Teste de segurança da régua",
        "rules": [
            {
                "id": "inactive_7d",
                "name": "Inatividade de sete dias",
                "version": 1,
                "conditions": {
                    "all": [
                        {"field": "days_since_contact", "op": "gte", "value": 7},
                        {"field": "opt_out", "op": "eq", "value": False},
                    ]
                },
                "action": {"channel": "whatsapp", "template_id": "retention_v1"},
            }
        ],
    }


async def _add_student(
    db_session,
    *,
    tenant_id: str,
    batch_id: str,
    matricula: str,
    risk_level: str | None,
    risk_score: float | None,
) -> Student:
    student = Student(
        tenant_id=tenant_id,
        batch_id=batch_id,
        matricula=matricula,
        nome=f"Aluno {matricula}",
        telefone="+5511999999999",
        email=f"{matricula}@example.test",
        risk_level=risk_level,
        risk_score=risk_score,
    )
    db_session.add(student)
    await db_session.flush()
    return student


@pytest.mark.asyncio
async def test_simulation_fails_closed_for_missing_or_invalid_risk_data(
    client, tenant_factory, db_session
):
    tenant, api_key = await tenant_factory(slug="risk-data")
    batch = UploadBatch(
        tenant_id=tenant.id,
        filename="test.csv",
        original_filename="test.csv",
        status="processed",
    )
    db_session.add(batch)
    await db_session.flush()

    await _add_student(
        db_session, tenant_id=tenant.id, batch_id=batch.id, matricula="MISSING-BOTH",
        risk_level=None, risk_score=None,
    )
    await _add_student(
        db_session, tenant_id=tenant.id, batch_id=batch.id, matricula="MISSING-SCORE",
        risk_level="critico", risk_score=None,
    )
    await _add_student(
        db_session, tenant_id=tenant.id, batch_id=batch.id, matricula="MISSING-LEVEL",
        risk_level=None, risk_score=95,
    )
    await _add_student(
        db_session, tenant_id=tenant.id, batch_id=batch.id, matricula="INVALID-LEVEL",
        risk_level="unknown", risk_score=95,
    )
    await _add_student(
        db_session, tenant_id=tenant.id, batch_id=batch.id, matricula="INVALID-SCORE",
        risk_level="critico", risk_score=101,
    )
    await db_session.commit()

    headers = {"X-API-Key": api_key}
    created = await client.post(
        "/api/v1/agents/retention/campaigns",
        headers=headers,
        json=_campaign_payload("risk-data"),
    )
    assert created.status_code == 201, created.text

    simulated = await client.post(
        f"/api/v1/agents/retention/campaigns/{created.json()['id']}/simulate",
        headers=headers,
    )
    assert simulated.status_code == 200, simulated.text
    result = simulated.json()
    assert result["students_evaluated"] == 5
    assert result["eligible"] == 0
    assert result["skipped"] == 5
    for decision in result["decisions"]:
        assert decision["eligible"] is False
        assert decision["matched_rules"] == []
        assert decision["blocked_reason"] == "missing_risk_data"
        assert "Bloqueio de segurança: missing_risk_data" in decision["reasons"]


@pytest.mark.asyncio
async def test_activating_new_version_pauses_previous_version(
    client, tenant_factory
):
    _tenant, api_key = await tenant_factory(slug="single-active")
    headers = {"X-API-Key": api_key}
    payload_v1 = _campaign_payload("single-active", name="Campanha v1")
    created_v1 = await client.post(
        "/api/v1/agents/retention/campaigns", headers=headers, json=payload_v1
    )
    assert created_v1.status_code == 201, created_v1.text
    v1_id = created_v1.json()["id"]

    activated_v1 = await client.patch(
        f"/api/v1/agents/retention/campaigns/{v1_id}/status",
        headers=headers,
        json={"status": "active"},
    )
    assert activated_v1.status_code == 200, activated_v1.text
    assert activated_v1.json()["status"] == "active"

    payload_v2 = _campaign_payload("single-active", name="Campanha v2")
    created_v2 = await client.post(
        f"/api/v1/agents/retention/campaigns/{v1_id}/versions",
        headers=headers,
        json=payload_v2,
    )
    assert created_v2.status_code == 201, created_v2.text
    assert created_v2.json()["version"] == 2
    v2_id = created_v2.json()["id"]

    activated_v2 = await client.patch(
        f"/api/v1/agents/retention/campaigns/{v2_id}/status",
        headers=headers,
        json={"status": "active"},
    )
    assert activated_v2.status_code == 200, activated_v2.text
    assert activated_v2.json()["status"] == "active"

    current_v1 = await client.get(
        f"/api/v1/agents/retention/campaigns/{v1_id}", headers=headers
    )
    current_v2 = await client.get(
        f"/api/v1/agents/retention/campaigns/{v2_id}", headers=headers
    )
    assert current_v1.json()["status"] == "paused"
    assert current_v2.json()["status"] == "active"

    active_list = await client.get(
        "/api/v1/agents/retention/campaigns?status=active", headers=headers
    )
    assert active_list.status_code == 200, active_list.text
    assert active_list.json()["count"] == 1
    assert [item["version"] for item in active_list.json()["campaigns"]] == [2]


@pytest.mark.asyncio
async def test_database_rejects_two_active_versions_for_same_campaign(
    client, tenant_factory, db_session
):
    _tenant, api_key = await tenant_factory(slug="active-constraint")
    headers = {"X-API-Key": api_key}
    created_v1 = await client.post(
        "/api/v1/agents/retention/campaigns",
        headers=headers,
        json=_campaign_payload("active-constraint", name="Versão v1"),
    )
    assert created_v1.status_code == 201, created_v1.text
    v1_id = created_v1.json()["id"]
    activated = await client.patch(
        f"/api/v1/agents/retention/campaigns/{v1_id}/status",
        headers=headers,
        json={"status": "active"},
    )
    assert activated.status_code == 200, activated.text

    created_v2 = await client.post(
        f"/api/v1/agents/retention/campaigns/{v1_id}/versions",
        headers=headers,
        json=_campaign_payload("active-constraint", name="Versão v2"),
    )
    assert created_v2.status_code == 201, created_v2.text
    v2_id = created_v2.json()["id"]

    with pytest.raises(IntegrityError):
        await db_session.execute(
            update(RetentionCampaign)
            .where(RetentionCampaign.id == v2_id)
            .values(status="active")
        )
        await db_session.commit()
    await db_session.rollback()




@pytest.mark.asyncio
async def test_dry_run_uses_highest_priority_rule_channel_template_and_audit(
    client, tenant_factory, db_session
):
    from sqlalchemy import select
    from app.models.intervention import InterventionLog

    tenant, api_key = await tenant_factory(slug="predictable-campaign")
    batch = UploadBatch(
        tenant_id=tenant.id,
        filename="priority.csv",
        original_filename="priority.csv",
        status="processed",
    )
    db_session.add(batch)
    await db_session.flush()
    student = await _add_student(
        db_session,
        tenant_id=tenant.id,
        batch_id=batch.id,
        matricula="PRIORITY-001",
        risk_level="critico",
        risk_score=95,
    )
    student.curso = "Engenharia"
    student.shap_top_factors = {"recommended_actions": ["Agendar atendimento"]}
    await db_session.commit()

    payload = _campaign_payload("predictable-campaign")
    payload["rules"] = [
        {
            "id": "critical_whatsapp",
            "name": "WhatsApp para críticos",
            "version": 1,
            "priority": 10,
            "conditions": {"all": [
                {"field": "risk_level", "op": "eq", "value": "critico"},
                {"field": "opt_out", "op": "eq", "value": False},
            ]},
            "action": {"channel": "whatsapp", "template_id": "critico_v1"},
        },
        {
            "id": "score_email",
            "name": "E-mail para score alto",
            "version": 1,
            "priority": 90,
            "conditions": {"all": [
                {"field": "risk_score", "op": "gte", "value": 90},
                {"field": "opt_out", "op": "eq", "value": False},
            ]},
            "action": {"channel": "email", "template_id": "score_alto_v1"},
        },
    ]
    headers = {"X-API-Key": api_key}
    created = await client.post(
        "/api/v1/agents/retention/campaigns", headers=headers, json=payload
    )
    assert created.status_code == 201, created.text
    campaign_id = created.json()["id"]

    simulation = await client.post(
        f"/api/v1/agents/retention/campaigns/{campaign_id}/simulate",
        headers=headers,
    )
    assert simulation.status_code == 200, simulation.text
    decision = simulation.json()["decisions"][0]
    assert decision["eligible"] is True
    assert decision["selected_rule"]["rule_id"] == "score_email"
    assert decision["selected_rule"]["priority"] == 90
    assert decision["selected_rule"]["action"] == {
        "channel": "email", "template_id": "score_alto_v1"
    }
    assert [item["rule_id"] for item in decision["rule_evaluations"]] == [
        "score_email", "critical_whatsapp"
    ]
    assert [item["selected"] for item in decision["rule_evaluations"]] == [True, False]
    assert len(decision["matched_rules"]) == 1

    activated = await client.patch(
        f"/api/v1/agents/retention/campaigns/{campaign_id}/status",
        headers=headers,
        json={"status": "active"},
    )
    assert activated.status_code == 200, activated.text

    executed = await client.post(
        f"/api/v1/agents/retention/campaigns/{campaign_id}/run-dry-run",
        headers=headers,
    )
    assert executed.status_code == 200, executed.text
    result = executed.json()
    assert result["eligible"] == 1
    assert len(result["execution"]) == 1
    assert result["execution"][0]["totals"]["dry_run"] == 1
    assert result["execution"][0]["by_channel"]["email"]["dry_run"] == 1
    assert "whatsapp" not in result["execution"][0]["by_channel"]

    logs = list((await db_session.execute(
        select(InterventionLog).where(
            InterventionLog.tenant_id == tenant.id,
            InterventionLog.campaign_id == campaign_id,
            InterventionLog.student_id == student.id,
        )
    )).scalars().all())
    assert len(logs) == 1
    log = logs[0]
    assert log.channel == "email"
    assert log.template_id == "score_alto_v1"
    assert log.status == "dry_run"
    assert "Ola, Aluno" in (log.message_preview or "")
    assert "coordenacao" in (log.message_preview or "")
    assert log.decision_context["campaign_version"] == 1
    assert log.decision_context["template_id"] == "score_alto_v1"
    assert log.decision_context["selected_rule"] == {
        "rule_id": "score_email",
        "rule_version": 1,
        "priority": 90,
        "channel": "email",
        "template_id": "score_alto_v1",
    }
    assert [item["rule_id"] for item in log.decision_context["evaluated_rules"]] == [
        "score_email", "critical_whatsapp"
    ]
    assert "queremos te ajudar a continuar" in log.decision_context["email_subject"]


@pytest.mark.asyncio
async def test_campaign_rejects_template_not_registered_for_selected_channel(
    client, tenant_factory
):
    _tenant, api_key = await tenant_factory(slug="template-contract")
    payload = _campaign_payload("template-contract")
    payload["rules"][0]["action"] = {
        "channel": "whatsapp",
        "template_id": "score_alto_v1",
    }
    response = await client.post(
        "/api/v1/agents/retention/campaigns",
        headers={"X-API-Key": api_key},
        json=payload,
    )
    assert response.status_code == 422
    assert "Template não suportado" in response.text

