"""Integration tests for tenant boundaries and campaign re-execution safeguards."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models.intervention import InterventionLog
from app.models.student import Student, UploadBatch


def _payload(slug: str) -> dict:
    return {
        "slug": slug,
        "name": "Campanha isolada",
        "description": "Contrato de isolamento multi-tenant",
        "rules": [
            {
                "id": "critical_score",
                "name": "Score crítico",
                "version": 1,
                "priority": 100,
                "conditions": {
                    "all": [
                        {"field": "risk_score", "op": "gte", "value": 90},
                        {"field": "opt_out", "op": "eq", "value": False},
                    ]
                },
                "action": {"channel": "whatsapp", "template_id": "retention_v1"},
            }
        ],
    }


@pytest.mark.asyncio
async def test_campaign_data_and_operations_are_isolated_by_tenant(
    client, tenant_factory
):
    tenant_a, key_a = await tenant_factory(slug="campaign-tenant-a")
    tenant_b, key_b = await tenant_factory(slug="campaign-tenant-b")
    headers_a = {"X-API-Key": key_a}
    headers_b = {"X-API-Key": key_b}

    created_a = await client.post(
        "/api/v1/agents/retention/campaigns",
        headers=headers_a,
        json=_payload("same-slug"),
    )
    assert created_a.status_code == 201, created_a.text
    campaign_a_id = created_a.json()["id"]
    assert created_a.json()["tenant_id"] == tenant_a.id

    # A different tenant may use the same slug; uniqueness is tenant-scoped.
    created_b = await client.post(
        "/api/v1/agents/retention/campaigns",
        headers=headers_b,
        json=_payload("same-slug"),
    )
    assert created_b.status_code == 201, created_b.text
    campaign_b_id = created_b.json()["id"]
    assert campaign_b_id != campaign_a_id
    assert created_b.json()["tenant_id"] == tenant_b.id

    own_a = await client.get(
        f"/api/v1/agents/retention/campaigns/{campaign_a_id}", headers=headers_a
    )
    own_b = await client.get(
        f"/api/v1/agents/retention/campaigns/{campaign_b_id}", headers=headers_b
    )
    assert own_a.status_code == 200
    assert own_b.status_code == 200

    foreign_routes = [
        ("GET", f"/api/v1/agents/retention/campaigns/{campaign_a_id}", None),
        ("POST", f"/api/v1/agents/retention/campaigns/{campaign_a_id}/simulate", None),
        ("PATCH", f"/api/v1/agents/retention/campaigns/{campaign_a_id}/status", {"status": "active"}),
        ("POST", f"/api/v1/agents/retention/campaigns/{campaign_a_id}/versions", _payload("same-slug")),
        ("POST", f"/api/v1/agents/retention/campaigns/{campaign_a_id}/run-dry-run", None),
    ]
    for method, route, body in foreign_routes:
        response = await client.request(method, route, headers=headers_b, json=body)
        assert response.status_code == 404, (
            f"{method} {route} leaked or exposed a foreign campaign: "
            f"{response.status_code} {response.text}"
        )

    list_a = await client.get("/api/v1/agents/retention/campaigns", headers=headers_a)
    list_b = await client.get("/api/v1/agents/retention/campaigns", headers=headers_b)
    ids_a = {item["id"] for item in list_a.json()["campaigns"]}
    ids_b = {item["id"] for item in list_b.json()["campaigns"]}
    assert ids_a == {campaign_a_id}
    assert ids_b == {campaign_b_id}
    assert ids_a.isdisjoint(ids_b)


@pytest.mark.asyncio
async def test_campaign_reexecution_does_not_repeat_dry_run_and_records_antispam(
    client, tenant_factory, db_session
):
    tenant, api_key = await tenant_factory(slug="campaign-idempotency")
    batch = UploadBatch(
        tenant_id=tenant.id,
        filename="idempotency.csv",
        original_filename="idempotency.csv",
        status="processed",
    )
    db_session.add(batch)
    await db_session.flush()
    student = Student(
        tenant_id=tenant.id,
        batch_id=batch.id,
        matricula="IDEMPOTENCY-001",
        nome="Aluno Idempotência",
        curso="Engenharia",
        risk_level="critico",
        risk_score=96,
        telefone="11988887777",
        email="idempotency@example.test",
        communication_opt_out=False,
        shap_top_factors={"recommended_actions": ["Agendar atendimento"]},
    )
    db_session.add(student)
    await db_session.commit()

    headers = {"X-API-Key": api_key}
    created = await client.post(
        "/api/v1/agents/retention/campaigns",
        headers=headers,
        json=_payload("idempotency-campaign"),
    )
    assert created.status_code == 201, created.text
    campaign_id = created.json()["id"]
    activated = await client.patch(
        f"/api/v1/agents/retention/campaigns/{campaign_id}/status",
        headers=headers,
        json={"status": "active"},
    )
    assert activated.status_code == 200, activated.text

    first = await client.post(
        f"/api/v1/agents/retention/campaigns/{campaign_id}/run-dry-run",
        headers=headers,
    )
    assert first.status_code == 200, first.text
    assert first.json()["execution"][0]["totals"]["dry_run"] == 1

    second = await client.post(
        f"/api/v1/agents/retention/campaigns/{campaign_id}/run-dry-run",
        headers=headers,
    )
    assert second.status_code == 200, second.text
    assert second.json()["execution"][0]["totals"]["dry_run"] == 0
    assert second.json()["execution"][0]["totals"]["skipped"] == 1

    logs = list((await db_session.execute(
        select(InterventionLog).where(
            InterventionLog.tenant_id == tenant.id,
            InterventionLog.campaign_id == campaign_id,
            InterventionLog.student_id == student.id,
        )
    )).scalars().all())
    dry_run_logs = [log for log in logs if log.status == "dry_run"]
    skipped_logs = [log for log in logs if log.status == "skipped"]
    assert len(dry_run_logs) == 1
    assert len(skipped_logs) == 1
    assert skipped_logs[0].skip_reason.startswith("anti-spam:")
    assert dry_run_logs[0].idempotency_key
    assert dry_run_logs[0].decision_context["selected_rule"]["rule_id"] == "critical_score"
    assert dry_run_logs[0].decision_context["template_id"] == "retention_v1"
