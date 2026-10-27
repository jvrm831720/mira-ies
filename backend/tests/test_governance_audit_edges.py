"""Targeted audit regression tests: tenant isolation and training-policy effective dates.

These tests intentionally exercise current public/API and policy boundaries without
changing application behavior. They do not establish exhaustive endpoint coverage.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.models.control_center import AdminPrincipal
from app.models.data_governance import TenantDataUsePolicy
from app.services.training_policy import resolve_training_policy


@pytest.mark.asyncio
async def test_risk_endpoints_do_not_disclose_another_tenants_student_or_batch(
    client, tenant_factory
):
    tenant_a, key_a = await tenant_factory(slug="audit-isolation-a", name="Audit A")
    _tenant_b, key_b = await tenant_factory(slug="audit-isolation-b", name="Audit B")
    csv_content = (
        b"matricula,nome,dias_atraso_boleto,dias_sem_login,presenca_percentual,nota_media\n"
        b"AUDIT001,Aluno Privado,50,40,30.0,2.0\n"
    )

    upload = await client.post(
        "/api/v1/upload",
        headers={"X-API-Key": key_a},
        files={"file": ("audit.csv", csv_content, "text/csv")},
        params={"auto_score": "true"},
    )
    assert upload.status_code == 201
    foreign_batch_id = upload.json()["batch"]["id"]

    owner_students = await client.get(
        "/api/v1/students", headers={"X-API-Key": key_a}
    )
    assert owner_students.status_code == 200
    owner_student = next(
        item for item in owner_students.json()["students"]
        if item["matricula"] == "AUDIT001"
    )

    foreign_headers = {"X-API-Key": key_b}
    foreign_student = await client.get(
        f"/api/v1/students/{owner_student['id']}/risk",
        headers=foreign_headers,
    )
    assert foreign_student.status_code == 404

    foreign_summary = await client.get(
        "/api/v1/risk/summary",
        headers=foreign_headers,
        params={"batch_id": foreign_batch_id},
    )
    assert foreign_summary.status_code == 200
    assert foreign_summary.json()["total_students"] == 0
    assert foreign_summary.json()["summary"]["sem_score"] == 0

    foreign_critical = await client.get(
        "/api/v1/risk/critical",
        headers=foreign_headers,
        params={"batch_id": foreign_batch_id},
    )
    assert foreign_critical.status_code == 200
    assert foreign_critical.json()["count"] == 0
    assert foreign_critical.json()["students"] == []

    foreign_score = await client.post(
        f"/api/v1/score/batch/{foreign_batch_id}",
        headers=foreign_headers,
    )
    assert foreign_score.status_code == 404


@pytest.mark.asyncio
async def test_future_dated_policy_does_not_take_effect_early(
    db_session, tenant_factory
):
    tenant, _ = await tenant_factory(slug="audit-policy-effective-date")
    admin = AdminPrincipal(
        email="audit-policy-admin@example.test",
        display_name="Audit Policy Admin",
        password_hash="not-a-real-password-hash",
        role="super_admin",
    )
    db_session.add(admin)
    await db_session.flush()

    now = datetime.now(timezone.utc)
    current_shared = TenantDataUsePolicy(
        tenant_id=tenant.id,
        mode="shared_training",
        contract_reference="audit-current",
        contract_version="v1",
        effective_at=now - timedelta(days=2),
        approved_by_admin_id=admin.id,
        evidence_reference="test-evidence://audit-current",
    )
    future_private = TenantDataUsePolicy(
        tenant_id=tenant.id,
        mode="institution_only",
        contract_reference="audit-future",
        contract_version="v2",
        effective_at=now + timedelta(days=1),
        approved_by_admin_id=admin.id,
        evidence_reference="test-evidence://audit-future",
    )
    db_session.add_all([current_shared, future_private])
    await db_session.commit()

    before_effective_date = await resolve_training_policy(
        db_session,
        tenant_id=tenant.id,
        purpose="shared_base_training",
        dataset_eligible=True,
        now=now,
    )
    after_effective_date = await resolve_training_policy(
        db_session,
        tenant_id=tenant.id,
        purpose="shared_base_training",
        dataset_eligible=True,
        now=now + timedelta(days=2),
    )

    assert before_effective_date.allowed is True
    assert before_effective_date.policy_id == current_shared.id
    assert after_effective_date.allowed is False
    assert after_effective_date.policy_id == future_private.id
    assert after_effective_date.mode == "institution_only"
