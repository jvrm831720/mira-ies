"""Testes de integração HTTP dos endpoints de sinais."""
from __future__ import annotations

import pytest


async def _seed_student(db_session, tenant, **fields):
    from app.models.student import Student, UploadBatch

    t, _key = tenant
    batch = UploadBatch(
        tenant_id=t.id,
        filename="signals-test.csv",
        original_filename="signals-test.csv",
        status="processed",
        total_rows=1,
        processed_rows=1,
    )
    db_session.add(batch)
    await db_session.flush()
    student = Student(
        batch_id=batch.id,
        tenant_id=t.id,
        matricula=fields.pop("matricula", "SIG001"),
        nome=fields.pop("nome", "Aluno Sinais"),
        is_active=fields.pop("is_active", True),
        **fields,
    )
    db_session.add(student)
    await db_session.commit()
    await db_session.refresh(student)
    return student


@pytest.mark.asyncio
async def test_signals_catalog_requires_auth(client):
    resp = await client.get("/api/v1/signals/catalog")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_signals_catalog_ok(client, auth_headers):
    resp = await client.get("/api/v1/signals/catalog", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 6
    ids = {s["id"] for s in body["signals"]}
    assert "risk_critical" in ids
    assert "risk_increase" in ids


@pytest.mark.asyncio
async def test_evaluate_student_critical(client, auth_headers, tenant, db_session):
    student = await _seed_student(
        db_session,
        tenant,
        risk_level="critico",
        risk_score=91.0,
        dias_atraso_boleto=None,
        dias_sem_login=None,
    )
    resp = await client.get(
        f"/api/v1/signals/evaluate?student_id={student.id}",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    by_id = {s["signal_id"]: s for s in body["signals"]}
    assert by_id["risk_critical"]["active"] is True
    assert by_id["missing_score"]["active"] is False
    assert by_id["financial_delay"]["insufficient_data"] is True


@pytest.mark.asyncio
async def test_evaluate_not_found_other_tenant(client, tenant_factory, db_session):
    tenant_a, key_a = await tenant_factory(slug="sig-a", name="Sig A")
    tenant_b, key_b = await tenant_factory(slug="sig-b", name="Sig B")

    from app.models.student import Student, UploadBatch

    batch = UploadBatch(
        tenant_id=tenant_a.id,
        filename="a.csv",
        original_filename="a.csv",
        status="processed",
    )
    db_session.add(batch)
    await db_session.flush()
    student = Student(
        batch_id=batch.id,
        tenant_id=tenant_a.id,
        matricula="XA1",
        nome="Only A",
        risk_level="critico",
        risk_score=80,
        is_active=True,
    )
    db_session.add(student)
    await db_session.commit()
    await db_session.refresh(student)

    resp = await client.get(
        f"/api/v1/signals/evaluate?student_id={student.id}",
        headers={"X-API-Key": key_b},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_summary_unique_students_multi_signal(client, auth_headers, tenant, db_session):
    await _seed_student(
        db_session,
        tenant,
        matricula="MULTI1",
        risk_level="critico",
        risk_score=95,
        dias_atraso_boleto=20,
        dias_sem_login=30,
    )
    resp = await client.get("/api/v1/signals/summary", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["scope"] == "tenant_full"
    assert body["total_students_in_tenant"] >= 1
    assert body["students_evaluated"] == body["total_students_in_tenant"] or body.get("truncated") is True
    assert body["students_with_active_signals"] >= 1
    activations = sum(body["activations_by_signal"].values())
    assert activations >= body["students_with_active_signals"]
    assert "page" not in body


@pytest.mark.asyncio
async def test_evaluate_missing_student_id_validation(client, auth_headers):
    resp = await client.get("/api/v1/signals/evaluate", headers=auth_headers)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_summary_requires_auth(client):
    resp = await client.get("/api/v1/signals/summary")
    assert resp.status_code == 401
