"""Regression tests for real risk-assessment history and tenant isolation."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.models.student import Student, UploadBatch
from app.models.risk_assessment import RiskAssessment


async def test_scoring_batch_persists_real_assessment_history(client, tenant, db_session):
    t, api_key = tenant
    batch = UploadBatch(
        tenant_id=t.id, filename="history.csv", original_filename="history.csv",
        status="received", total_rows=1, processed_rows=1,
    )
    db_session.add(batch)
    await db_session.flush()
    student = Student(
        tenant_id=t.id, batch_id=batch.id, matricula="H-001", nome="Histórico Real",
        curso="Direito", dias_atraso_boleto=40, recorrencia_atrasos=2,
        dias_sem_login=30, presenca_percentual=50, nota_media=4, reprovacoes=1,
    )
    db_session.add(student)
    await db_session.commit()

    response = await client.post("/api/v1/score/batch/" + batch.id, headers={"X-API-Key": api_key})
    assert response.status_code == 200, response.text
    history = await client.get("/api/v1/risk/history", headers={"X-API-Key": api_key})
    assert history.status_code == 200, history.text
    body = history.json()
    assert body["total_assessments"] == 1
    assert body["assessments"][0]["student_id"] == student.id
    assert body["assessments"][0]["model_version"]
    assert body["assessments"][0]["score"] >= 0
    assert body["timeline"]


async def test_risk_history_is_tenant_scoped_and_unknown_student_is_404(client, tenant_factory, db_session):
    tenant_a, _key_a = await tenant_factory(slug="history-a")
    _tenant_b, key_b = await tenant_factory(slug="history-b")
    batch = UploadBatch(
        tenant_id=tenant_a.id, filename="a.csv", original_filename="a.csv",
        status="scored", total_rows=1, processed_rows=1,
    )
    db_session.add(batch)
    await db_session.flush()
    student = Student(tenant_id=tenant_a.id, batch_id=batch.id, matricula="A-001", nome="Aluno A", curso="Direito")
    db_session.add(student)
    await db_session.flush()
    db_session.add(RiskAssessment(
        tenant_id=tenant_a.id, student_id=student.id, batch_id=batch.id,
        scoring_run_id=str(uuid4()), evaluated_at=datetime.now(timezone.utc),
        score=72, risk_level="critico", model_version="test-v1", model_scope="base",
        model_score=70, dynamic_adjustment=2, features_snapshot={},
        explanation={"available": False}, context={"source": "test"},
    ))
    await db_session.commit()

    foreign = await client.get("/api/v1/risk/history", headers={"X-API-Key": key_b})
    assert foreign.status_code == 200
    assert foreign.json()["total_assessments"] == 0
    student_history = await client.get("/api/v1/students/" + student.id + "/risk/history", headers={"X-API-Key": key_b})
    assert student_history.status_code == 404


async def test_risk_history_rejects_invalid_range_and_risk_level(client, auth_headers):
    now = datetime.now(timezone.utc)
    invalid_range = await client.get(
        "/api/v1/risk/history", headers=auth_headers,
        params={"from": (now + timedelta(days=1)).isoformat(), "to": now.isoformat()},
    )
    assert invalid_range.status_code == 422
    invalid_level = await client.get("/api/v1/risk/history", headers=auth_headers, params={"risk_level": "urgentissimo"})
    assert invalid_level.status_code == 422


async def test_score_comparison_never_compares_different_model_versions():
    from app.api.scoring import _change_type
    now = datetime.now(timezone.utc)
    current = RiskAssessment(
        tenant_id=str(uuid4()), student_id=str(uuid4()), scoring_run_id=str(uuid4()),
        evaluated_at=now, score=80, risk_level="critico", model_version="v2",
        model_scope="base", features_snapshot={},
    )
    previous = RiskAssessment(
        tenant_id=current.tenant_id, student_id=current.student_id, scoring_run_id=str(uuid4()),
        evaluated_at=now - timedelta(days=1), score=40, risk_level="medio",
        model_version="v1", model_scope="base", features_snapshot={},
    )
    kind, delta = _change_type(current, previous)
    assert kind == "mudanca_modelo"
    assert delta is None



async def test_risk_history_compares_latest_assessment_to_previous_within_period(client, tenant, db_session):
    t, api_key = tenant
    batch = UploadBatch(
        tenant_id=t.id, filename="movement.csv", original_filename="movement.csv",
        status="scored", total_rows=1, processed_rows=1,
    )
    db_session.add(batch)
    await db_session.flush()
    student = Student(tenant_id=t.id, batch_id=batch.id, matricula="M-001", nome="Movimentação", curso="Medicina")
    db_session.add(student)
    await db_session.flush()
    now = datetime.now(timezone.utc)
    for days_ago, score, level in [(2, 42.0, "medio"), (1, 67.0, "medio")]:
        db_session.add(RiskAssessment(
            tenant_id=t.id, student_id=student.id, batch_id=batch.id,
            scoring_run_id=str(uuid4()), evaluated_at=now - timedelta(days=days_ago),
            score=score, risk_level=level, model_version="base-v1", model_scope="base",
            model_score=score, dynamic_adjustment=0, features_snapshot={},
            explanation={"available": False}, context={"source": "test"},
        ))
    await db_session.commit()

    response = await client.get("/api/v1/risk/history", headers={"X-API-Key": api_key})
    assert response.status_code == 200, response.text
    movement = next(item for item in response.json()["movements"] if item["student_id"] == student.id)
    assert movement["previous_score"] == 42.0
    assert movement["current_score"] == 67.0
    assert movement["delta"] == 25.0
    assert movement["change_type"] == "risco_aumentou"



async def test_forced_batch_score_requires_and_reuses_idempotency_key(client, tenant, db_session):
    t, api_key = tenant
    batch = UploadBatch(
        tenant_id=t.id, filename="retry.csv", original_filename="retry.csv",
        status="received", total_rows=1, processed_rows=1,
    )
    db_session.add(batch)
    await db_session.flush()
    db_session.add(Student(
        tenant_id=t.id, batch_id=batch.id, matricula="R-001", nome="Retry Seguro",
        curso="Direito", dias_atraso_boleto=25, dias_sem_login=20,
        presenca_percentual=60, nota_media=5,
    ))
    await db_session.commit()
    headers = {"X-API-Key": api_key}

    missing_key = await client.post(
        "/api/v1/score/batch/" + batch.id, headers=headers, params={"force": "true"}
    )
    assert missing_key.status_code == 422

    headers["Idempotency-Key"] = "retry-stable-key"
    first = await client.post(
        "/api/v1/score/batch/" + batch.id, headers=headers, params={"force": "true"}
    )
    second = await client.post(
        "/api/v1/score/batch/" + batch.id, headers=headers, params={"force": "true"}
    )
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert second.json()["idempotent_replay"] is True
    history = await client.get("/api/v1/risk/history", headers={"X-API-Key": api_key})
    assert history.status_code == 200
    assert history.json()["total_assessments"] == 1
