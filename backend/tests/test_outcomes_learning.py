"""Testes de integracao: outcomes (learning loop) e treino de modelo por tenant."""
import random


async def test_register_outcome_creates_training_event(client, auth_headers, tenant):
    t, _raw_key = tenant
    resp = await client.post(
        "/api/v1/outcomes",
        headers=auth_headers,
        json={"tenant_slug": t.slug, "outcomes": [{"matricula": "EVD1", "outcome": "evadiu"}]},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["created"] == 1

    events = await client.get(
        "/api/v1/training-events", headers=auth_headers, params={"tenant_slug": t.slug, "labeled_only": True}
    )
    assert events.json()["count"] == 1
    assert events.json()["events"][0]["label"] == 1


async def test_register_outcome_rejects_unknown_outcome_value(client, auth_headers, tenant):
    t, _raw_key = tenant
    resp = await client.post(
        "/api/v1/outcomes",
        headers=auth_headers,
        json={"tenant_slug": t.slug, "outcomes": [{"matricula": "X", "outcome": "invalido"}]},
    )
    assert resp.status_code == 201
    assert resp.json()["errors"][0]["matricula"] == "X"


async def test_outcomes_caps_batch_size(client, auth_headers, tenant):
    t, _raw_key = tenant
    too_many = [{"matricula": str(i), "outcome": "ativo"} for i in range(2001)]
    resp = await client.post(
        "/api/v1/outcomes", headers=auth_headers, json={"tenant_slug": t.slug, "outcomes": too_many}
    )
    assert resp.status_code == 422


async def test_tenant_train_blocked_when_not_ready(client, auth_headers, tenant):
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


async def test_tenant_train_force_with_enough_labels_trains_and_can_activate(client, auth_headers, tenant):
    t, _raw_key = tenant
    rng = random.Random(42)
    outcomes = []
    for i in range(30):
        is_evasion = i % 3 == 0
        outcomes.append({
            "matricula": f"T{i}",
            "outcome": "evadiu" if is_evasion else "ativo",
        })
    resp = await client.post(
        "/api/v1/outcomes", headers=auth_headers, json={"tenant_slug": t.slug, "outcomes": outcomes}
    )
    assert resp.status_code == 201

    resp_train = await client.post(
        f"/api/v1/tenants/{t.slug}/train", headers=auth_headers,
        params={"force": "true", "force_activate": "true"},
    )
    assert resp_train.status_code == 200
    body = resp_train.json()
    assert body["status"] == "trained"
    assert body["activated"] is True
    assert body["metrics"]["n_tenant_events"] == 30

    resp_models = await client.get(f"/api/v1/tenants/{t.slug}/models", headers=auth_headers)
    assert resp_models.status_code == 200
    assert any(m["is_active"] for m in resp_models.json()["models"])

    resp_deactivate = await client.post(f"/api/v1/tenants/{t.slug}/models/deactivate", headers=auth_headers)
    assert resp_deactivate.status_code == 200
    assert resp_deactivate.json()["active_model"] == "base"


async def test_tenant_learning_status_requires_matching_tenant(client, tenant_factory):
    _t_a, key_a = await tenant_factory(slug="learn-a", name="Learn A")
    t_b, _key_b = await tenant_factory(slug="learn-b", name="Learn B")
    resp = await client.get(f"/api/v1/tenants/{t_b.slug}/learning", headers={"X-API-Key": key_a})
    assert resp.status_code == 403
