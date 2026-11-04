"""Testes de integração: outcomes e rótulos do alvo de 90 dias."""
from datetime import datetime, timedelta, timezone

from app.models.tenant import TrainingEvent
from app.ml.targets import TARGET_DEFINITION_VERSION


def _training_event(tenant, matricula, scored_at, *, label=None, target_definition=None):
    return TrainingEvent(
        tenant_id=tenant.id,
        matricula=matricula,
        scored_at=scored_at,
        features_snapshot={
            "dias_atraso_boleto": 5,
            "recorrencia_atrasos": 1,
            "dias_sem_login": 8,
            "presenca_percentual": 85,
            "nota_media": 7,
            "reprovacoes": 0,
            "semestre": 2,
        },
        label=label,
        target_definition=target_definition,
    )


async def test_register_outcome_creates_target_label_for_matching_score(client, auth_headers, tenant, db_session):
    t, _raw_key = tenant
    now = datetime.now(timezone.utc)
    event = _training_event(t, "EVD1", now - timedelta(days=60))
    db_session.add(event)
    await db_session.commit()

    resp = await client.post(
        "/api/v1/outcomes",
        headers=auth_headers,
        json={"tenant_slug": t.slug, "outcomes": [{
            "matricula": "EVD1", "outcome": "evadiu",
            "observed_at": (now - timedelta(days=30)).isoformat(),
        }]},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["updated"] == 1
    assert body["created"] == 0
    assert body["labeled"] == 1
    assert body["target_definition"] == TARGET_DEFINITION_VERSION

    events = await client.get(
        "/api/v1/training-events", headers=auth_headers,
        params={"tenant_slug": t.slug, "labeled_only": True},
    )
    assert events.json()["count"] == 1
    assert events.json()["events"][0]["label"] == 1
    assert events.json()["events"][0]["outcome_at"] is not None
    assert events.json()["events"][0]["target_definition"] == TARGET_DEFINITION_VERSION


async def test_transfer_is_recorded_but_excluded_from_training(client, auth_headers, tenant, db_session):
    t, _raw_key = tenant
    now = datetime.now(timezone.utc)
    db_session.add(_training_event(t, "TR1", now - timedelta(days=120)))
    await db_session.commit()

    resp = await client.post(
        "/api/v1/outcomes", headers=auth_headers,
        json={"tenant_slug": t.slug, "outcomes": [{
            "matricula": "TR1", "outcome": "transferiu",
            "observed_at": (now - timedelta(days=10)).isoformat(),
        }]},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["labeled"] == 0
    assert body["excluded_from_training"][0]["reason"] == "excluded_competing_outcome"
    assert body["learning"]["labeled_events"] == 0


async def test_rematriculado_is_a_supported_permanence_outcome(client, auth_headers, tenant, db_session):
    t, _raw_key = tenant
    now = datetime.now(timezone.utc)
    scored_at = now - timedelta(days=120)
    event = _training_event(t, "RE-1", scored_at)
    db_session.add(event)
    await db_session.commit()

    resp = await client.post(
        "/api/v1/outcomes",
        headers=auth_headers,
        json={"tenant_slug": t.slug, "outcomes": [{
            "matricula": "RE-1",
            "training_event_id": event.id,
            "outcome": "rematriculado",
            "observed_at": (scored_at + timedelta(days=30)).isoformat(),
            "academic_period": "2026.2",
            "source": "jacad",
        }]},
    )
    assert resp.status_code == 201
    assert resp.json()["updated"] == 1
    assert resp.json()["labeled"] == 1
    await db_session.refresh(event)
    assert event.outcome == "rematriculado"
    assert event.outcome_period == "2026.2"
    assert event.outcome_source == "jacad"
    assert event.label == 0


async def test_active_outcome_waits_for_90_day_window_then_becomes_negative(
    client, auth_headers, tenant, db_session,
):
    t, _raw_key = tenant
    now = datetime.now(timezone.utc)
    scored_at = now - timedelta(days=120)
    event = _training_event(t, "AT1", scored_at)
    db_session.add(event)
    await db_session.commit()

    immature = await client.post(
        "/api/v1/outcomes", headers=auth_headers,
        json={"tenant_slug": t.slug, "outcomes": [{
            "matricula": "AT1", "training_event_id": event.id, "outcome": "ativo",
            "observed_at": (scored_at + timedelta(days=30)).isoformat(),
        }]},
    )
    assert immature.json()["labeled"] == 0
    assert immature.json()["deferred"][0]["reason"] == "pending_90_day_observation"

    mature = await client.post(
        "/api/v1/outcomes", headers=auth_headers,
        json={"tenant_slug": t.slug, "outcomes": [{
            "matricula": "AT1", "training_event_id": event.id, "outcome": "ativo",
            "observed_at": (now - timedelta(days=1)).isoformat(),
        }]},
    )
    assert mature.json()["labeled"] == 1
    assert mature.json()["learning"]["labeled_events"] == 1


async def test_register_outcome_rejects_unknown_outcome_value(client, auth_headers, tenant):
    t, _raw_key = tenant
    resp = await client.post(
        "/api/v1/outcomes",
        headers=auth_headers,
        json={"tenant_slug": t.slug, "outcomes": [{"matricula": "X", "outcome": "invalido"}]},
    )
    assert resp.status_code == 201
    assert resp.json()["errors"][0]["matricula"] == "X"


async def test_outcome_without_scored_snapshot_is_not_added_to_training(client, auth_headers, tenant):
    t, _raw_key = tenant
    resp = await client.post(
        "/api/v1/outcomes", headers=auth_headers,
        json={"tenant_slug": t.slug, "outcomes": [{"matricula": "NO-SCORE", "outcome": "evadiu"}]},
    )
    assert resp.status_code == 201
    assert "snapshot de pontuação não encontrado" in resp.json()["errors"][0]["error"]
    assert resp.json()["created"] == 0


async def test_explicit_training_event_id_cannot_label_another_matricula(
    client, auth_headers, tenant, db_session,
):
    t, _raw_key = tenant
    now = datetime.now(timezone.utc)
    event = _training_event(t, "STUDENT-A", now - timedelta(days=60))
    db_session.add(event)
    await db_session.commit()

    resp = await client.post(
        "/api/v1/outcomes", headers=auth_headers,
        json={"tenant_slug": t.slug, "outcomes": [{
            "matricula": "STUDENT-B", "training_event_id": event.id,
            "outcome": "evadiu", "observed_at": (now - timedelta(days=30)).isoformat(),
        }]},
    )
    assert resp.status_code == 201
    assert "não corresponde à matrícula" in resp.json()["errors"][0]["error"]
    events = await client.get("/api/v1/training-events", headers=auth_headers, params={"tenant_slug": t.slug})
    assert events.json()["events"][0]["outcome"] is None


async def test_outcomes_caps_batch_size(client, auth_headers, tenant):
    t, _raw_key = tenant
    too_many = [{"matricula": str(i), "outcome": "ativo"} for i in range(2001)]
    resp = await client.post(
        "/api/v1/outcomes", headers=auth_headers,
        json={"tenant_slug": t.slug, "outcomes": too_many},
    )
    assert resp.status_code == 422


async def test_tenant_train_blocked_when_not_ready(
    client, auth_headers, tenant, institutional_training_authorization,
):
    t, _raw_key = tenant
    resp = await client.post(f"/api/v1/tenants/{t.slug}/train", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "not_ready"


async def test_tenant_train_force_blocked_when_allow_force_train_false(client, auth_headers, tenant, monkeypatch):
    import app.ml.tenant_train as tenant_train_module
    t, _raw_key = tenant
    monkeypatch.setattr(tenant_train_module.get_settings(), "allow_force_train", False)
    resp = await client.post(f"/api/v1/tenants/{t.slug}/train", headers=auth_headers, params={"force": "true"})
    assert resp.status_code == 400
    assert "ALLOW_FORCE_TRAIN" in resp.json()["detail"]


async def test_tenant_train_uses_only_mature_target_labels(
    client, auth_headers, tenant, db_session, institutional_training_authorization,
):
    t, _raw_key = tenant
    now = datetime.now(timezone.utc)
    outcomes = []
    for i in range(30):
        is_evasion = i % 3 == 0
        matricula = f"T{i}"
        scored_at = now - timedelta(days=800 - i * 20)
        observed_at = scored_at + timedelta(days=30 if is_evasion else 100)
        db_session.add(_training_event(t, matricula, scored_at))
        outcomes.append({
            "matricula": matricula,
            "outcome": "evadiu" if is_evasion else "ativo",
            "observed_at": observed_at.isoformat(),
        })
    await db_session.commit()

    resp = await client.post(
        "/api/v1/outcomes", headers=auth_headers,
        json={"tenant_slug": t.slug, "outcomes": outcomes},
    )
    assert resp.status_code == 201
    assert resp.json()["labeled"] == 30

    resp_train = await client.post(
        f"/api/v1/tenants/{t.slug}/train", headers=auth_headers,
        params={"force": "true", "force_activate": "true"},
    )
    assert resp_train.status_code == 200
    body = resp_train.json()
    # Training creates a candidate only; activation requires separate human approval.
    assert body["status"] == "candidate"
    assert body["activated"] is False
    assert body["metrics"]["n_tenant_events"] == 30
    metrics = body["metrics"]
    assert metrics["n_synthetic_training_rows"] > 0
    real_and_excluded = (
        metrics["n_tenant_train_real_events"]
        + metrics["n_tenant_calibration_real_events"]
        + metrics["n_tenant_test_real_events"]
        + metrics["n_temporally_excluded_events"]
    )
    ratio_total = (
        metrics["temporal_train_ratio"]
        + metrics["temporal_calibration_ratio"]
        + metrics["temporal_test_ratio"]
    )
    assert real_and_excluded == 30
    assert abs(ratio_total - 1.0) < 0.001

    resp_models = await client.get(f"/api/v1/tenants/{t.slug}/models", headers=auth_headers)
    assert resp_models.status_code == 200
    candidate = next(m for m in resp_models.json()["models"] if m["lifecycle_status"] == "candidate")
    assert candidate["is_active"] is False
    assert resp_models.json()["active_model"] == "base"  # baseline is a fallback, not a tenant artifact
    assert resp_models.json()["active_model_id"] is None

    # Tenant API keys identify an institution, not a human admin. Lifecycle
    # actions must reject this request even when a reason is supplied.
    resp_deactivate = await client.post(
        f"/api/v1/tenants/{t.slug}/models/deactivate", headers=auth_headers,
        json={"reason": "Validar retorno seguro ao baseline"},
    )
    assert resp_deactivate.status_code == 403
    assert "sessão de usuário admin identificada" in resp_deactivate.json()["detail"]


async def test_legacy_labels_are_not_counted_as_ready(client, auth_headers, tenant, db_session):
    t, _raw_key = tenant
    db_session.add(_training_event(t, "LEGACY", datetime.now(timezone.utc) - timedelta(days=120), label=1))
    await db_session.commit()

    resp = await client.get(f"/api/v1/tenants/{t.slug}/learning", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["labeled_events"] == 0
    assert resp.json()["legacy_labeled_events"] == 1


async def test_legacy_active_model_is_reported_as_base_fallback(client, auth_headers, tenant, db_session):
    from uuid import uuid4
    from app.models.tenant import ModelArtifact

    t, _raw_key = tenant
    artifact = ModelArtifact(
        id=str(uuid4()), tenant_id=t.id, name="legacy-model", version="old",
        scope="tenant", storage_path="/tmp/legacy-model.joblib",
        metrics={"auc": 0.8}, is_active=True,
    )
    db_session.add(artifact)
    t.active_model_id = artifact.id
    await db_session.commit()

    resp = await client.get(f"/api/v1/tenants/{t.slug}/models", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["active_model"] == "base"
    assert body["active_model_id"] is None
    stale = next(m for m in body["models"] if m["id"] == artifact.id)
    assert stale["is_active"] is True
    assert stale["is_used_for_scoring"] is False


async def test_tenant_learning_status_requires_matching_tenant(client, tenant_factory):
    _t_a, key_a = await tenant_factory(slug="learn-a", name="Learn A")
    t_b, _key_b = await tenant_factory(slug="learn-b", name="Learn B")
    resp = await client.get(f"/api/v1/tenants/{t_b.slug}/learning", headers={"X-API-Key": key_a})
    assert resp.status_code == 403
