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


