"""Native education Wave 1: no mock student identity and no live financial operations.

Integration tests require isolated PostgreSQL; they are NOT evidence of passing
unless actually run. The product stays disabled until an approved test run.
"""
from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from pydantic import ValidationError

from app.api.native_academic import (
    AcademicRecordBatch, import_manual_records, institution_records,
    AcademicRecordInput, _hash_token, _make_token, _now, _student_profile,
    _tenant_from_token,
)
from app.core.auth import AuthContext
from app.core.config import get_settings
from app.models.auth import User
from app.models.native_academic import MiraAcademicRecord, MiraStudentPortalInvite
from app.models.student import Student, UploadBatch


def test_token_is_tenant_scoped_and_tamper_rejected():
    tenant_id = str(uuid4())
    token = _make_token(tenant_id)
    assert _tenant_from_token(token) == tenant_id
    assert len(token) > 70
    assert token not in _hash_token(token)
    with pytest.raises(HTTPException):
        _tenant_from_token("not-an-invite")
    with pytest.raises(HTTPException):
        _tenant_from_token(token + "..")


def test_academic_input_has_strict_kind_boundaries():
    grade = AcademicRecordInput(
        kind="assessment", source_record_id="grade-1",
        title="Matemática", grade=Decimal("8.50"), max_grade=Decimal("10"),
    )
    assert grade.grade == Decimal("8.50")
    with pytest.raises(ValidationError):
        AcademicRecordInput(kind="fee", title="Mensalidade",
                            source_record_id="fee-1", amount=Decimal("250"))
    with pytest.raises(ValidationError):
        AcademicRecordInput(kind="attendance", title="Aula 1", source_record_id="att-1")
    with pytest.raises(ValidationError):
        AcademicRecordInput(kind="assessment", title="Prova", source_record_id="a",
                            grade=Decimal("12"), max_grade=Decimal("10"))
    with pytest.raises(ValidationError):
        AcademicRecordInput(kind="enrollment", title="Curso", source_record_id="1",
                            amount=Decimal("100"), currency="BRL")


async def _seed_student(db, tenant, *, id_suffix="a"):
    await db.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": tenant.id})
    tenant.segment = "higher_education"
    batch = UploadBatch(
        tenant_id=tenant.id, filename=f"seed-{id_suffix}.csv",
        original_filename=f"seed-{id_suffix}.csv",
    )
    db.add(batch)
    await db.flush()
    student = Student(
        tenant_id=tenant.id, batch_id=batch.id,
        matricula=f"A-{id_suffix}", nome=f"Aluno {id_suffix}",
        email=f"student-{id_suffix}@example.test",
        curso="Direito", presenca_percentual=78.0,
        nota_media=7.0, risk_score=95, saldo_devedor=500.0,
    )
    db.add(student)
    await db.flush()
    return student


async def _seed_invite(db, tenant, student):
    await db.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": tenant.id})
    admin = User(
        tenant_id=tenant.id, display_name="Equipe autorizada",
        email=f"admin-{uuid4().hex}@example.test",
        password_hash="test-hash", role="admin",
    )
    db.add(admin)
    await db.flush()
    token = _make_token(tenant.id)
    db.add(MiraStudentPortalInvite(
        tenant_id=tenant.id, student_id=student.id,
        issued_by_user_id=admin.id, token_hash=_hash_token(token),
        expires_at=_now() + timedelta(minutes=15),
    ))
    await db.commit()
    return token


def test_portal_profile_does_not_leak_internal_scoring():
    student = Student(
        matricula="123", nome="Ana Teste", batch_id=str(uuid4()),
        risk_score=99.0, saldo_devedor=200.0,
        shap_top_factors={"secret": "internal"},
    )
    data = _student_profile(student, "Instituição Teste")
    assert data["name"] == "Ana Teste"
    for hidden in ("risk_score", "risk_level", "saldo_devedor",
                   "shap_top_factors", "email", "telefone"):
        assert hidden not in data


async def test_portal_disabled_by_default(client):
    response = await client.get("/api/v1/student-portal/me")
    assert response.status_code == 503


async def test_portal_claim_requires_header(client, db_session, tenant_factory, monkeypatch):
    monkeypatch.setattr(get_settings(), "student_portal_enabled", True)
    tenant, _ = await tenant_factory(slug="portal-csrf")
    student = await _seed_student(db_session, tenant, id_suffix="csrf")
    token = await _seed_invite(db_session, tenant, student)
    response = await client.post("/api/v1/student-portal/claim", json={"token": token})
    assert response.status_code == 403
    # A rejected CSRF request cannot consume an invitation.
    accepted = await client.post(
        "/api/v1/student-portal/claim",
        headers={"X-Mira-Portal-Action": "1"},
        json={"token": token},
    )
    assert accepted.status_code == 200


async def test_self_service_is_private_replay_safe_and_revocable(
    client, db_session, tenant_factory, monkeypatch,
):
    monkeypatch.setattr(get_settings(), "student_portal_enabled", True)
    tenant_a, _ = await tenant_factory(slug="portal-a")
    tenant_b, _ = await tenant_factory(slug="portal-b")
    a = await _seed_student(db_session, tenant_a, id_suffix="alice")
    b = await _seed_student(db_session, tenant_b, id_suffix="bob")
    await db_session.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": tenant_a.id})
    db_session.add(MiraAcademicRecord(
        tenant_id=tenant_a.id, student_id=a.id,
        kind="enrollment", source="manual", source_record_id="enroll-a",
        title="Direito", status="active", event_date=date(2026, 8, 1),
    ))
    await db_session.commit()
    await db_session.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": tenant_b.id})
    db_session.add(MiraAcademicRecord(
        tenant_id=tenant_b.id, student_id=b.id,
        kind="assessment", source="manual", source_record_id="score-b",
        title="Matemática de Bob", grade=Decimal("9"),
        max_grade=Decimal("10"), status="approved",
    ))
    token = await _seed_invite(db_session, tenant_a, a)

    unauth = await client.get("/api/v1/student-portal/records")
    assert unauth.status_code == 401

    claim = await client.post(
        "/api/v1/student-portal/claim",
        headers={"X-Mira-Portal-Action": "1"},
        json={"token": token},
    )
    assert claim.status_code == 200
    assert "httponly" in claim.headers["set-cookie"].lower()
    assert "samesite=lax" in claim.headers["set-cookie"].lower()
    me = await client.get("/api/v1/student-portal/me")
    assert me.status_code == 200
    assert me.json()["student"]["student_id"] == a.id
    assert "risk_score" not in me.text
    assert "saldo_devedor" not in me.text

    records = await client.get("/api/v1/student-portal/records")
    assert records.status_code == 200
    assert [item["title"] for item in records.json()["items"]] == ["Direito"]
    assert "Matemática de Bob" not in records.text

    replay = await client.post(
        "/api/v1/student-portal/claim",
        headers={"X-Mira-Portal-Action": "1"},
        json={"token": token},
    )
    assert replay.status_code == 401

    logout = await client.post(
        "/api/v1/student-portal/logout",
        headers={"X-Mira-Portal-Action": "1"},
    )
    assert logout.status_code == 200
    assert (await client.get("/api/v1/student-portal/me")).status_code == 401


async def test_billing_tenant_is_denied_portal_claim(client, db_session, tenant_factory, monkeypatch):
    monkeypatch.setattr(get_settings(), "student_portal_enabled", True)
    tenant, _ = await tenant_factory(slug="not-an-ies")
    student = await _seed_student(db_session, tenant, id_suffix="billing")
    tenant.segment = "billing"
    token = await _seed_invite(db_session, tenant, student)
    response = await client.post(
        "/api/v1/student-portal/claim",
        headers={"X-Mira-Portal-Action": "1"},
        json={"token": token},
    )
    assert response.status_code == 401


async def test_staff_cannot_read_another_ies_records(db_session, tenant_factory, monkeypatch):
    monkeypatch.setattr(get_settings(), "native_academic_enabled", True)
    a, _ = await tenant_factory(slug="academic-a")
    b, _ = await tenant_factory(slug="academic-b")
    a.segment = "higher_education"
    b_student = await _seed_student(db_session, b, id_suffix="cross-tenant")
    await db_session.commit()
    auth = AuthContext(
        tenant=a, tenant_id=a.id, tenant_slug=a.slug,
        user_id=str(uuid4()), session_id=str(uuid4()), role="admin",
    )
    await db_session.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": a.id})
    with pytest.raises(HTTPException) as exc:
        await institution_records(b_student.id, None, auth, db_session)
    assert exc.value.status_code == 404


async def test_manual_academic_upsert_is_idempotent(db_session, tenant_factory, monkeypatch):
    monkeypatch.setattr(get_settings(), "native_academic_enabled", True)
    tenant, _ = await tenant_factory(slug="academic-upsert")
    student = await _seed_student(db_session, tenant, id_suffix="upsert")
    await db_session.commit()
    auth = AuthContext(
        tenant=tenant, tenant_id=tenant.id, tenant_slug=tenant.slug,
        user_id=str(uuid4()), session_id=str(uuid4()), role="admin",
    )
    first = AcademicRecordBatch(records=[AcademicRecordInput(
        kind="assessment", source_record_id="student-42-term-1",
        title="Avaliação de matemática", academic_period="2026-2",
        status="published", grade=Decimal("8"), max_grade=Decimal("10"),
    )])
    second = AcademicRecordBatch(records=[AcademicRecordInput(
        kind="assessment", source_record_id="student-42-term-1",
        title="Avaliação de matemática", academic_period="2026-2",
        status="corrected", grade=Decimal("9"), max_grade=Decimal("10"),
    )])
    await db_session.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": tenant.id})
    assert (await import_manual_records(student.id, first, auth, db_session))["records_received"] == 1
    await db_session.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": tenant.id})
    assert (await import_manual_records(student.id, second, auth, db_session))["records_received"] == 1
    await db_session.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": tenant.id})
    result = await institution_records(student.id, "assessment", auth, db_session)
    assert len(result["items"]) == 1
    assert result["items"][0]["grade"] == "9.00"
    assert result["items"][0]["status"] == "corrected"
