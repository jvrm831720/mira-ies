"""Testes de integracao: autenticacao por API key e isolamento multi-tenant."""


async def test_missing_api_key_returns_401(client):
    resp = await client.get("/api/v1/students")
    assert resp.status_code == 401


async def test_invalid_api_key_returns_401(client):
    resp = await client.get("/api/v1/students", headers={"X-API-Key": "bkn_not_a_real_key"})
    assert resp.status_code == 401


async def test_valid_api_key_returns_200(client, auth_headers):
    resp = await client.get("/api/v1/students", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["students"] == []


async def test_inactive_tenant_is_rejected(client, tenant_factory, db_session):
    tenant, raw_key = await tenant_factory(slug="inactive-co", name="Inactive Co")
    tenant.is_active = False
    await db_session.commit()
    resp = await client.get("/api/v1/students", headers={"X-API-Key": raw_key})
    assert resp.status_code == 401


async def test_bearer_token_header_is_accepted(client, tenant):
    _t, raw_key = tenant
    resp = await client.get("/api/v1/students", headers={"Authorization": f"Bearer {raw_key}"})
    assert resp.status_code == 200


async def test_tenant_isolation_students_not_visible_across_tenants(client, tenant_factory):
    tenant_a, key_a = await tenant_factory(slug="tenant-a", name="Tenant A")
    tenant_b, key_b = await tenant_factory(slug="tenant-b", name="Tenant B")

    csv_content = b"matricula,nome\nA001,Aluno A\n"
    resp = await client.post(
        "/api/v1/upload",
        headers={"X-API-Key": key_a},
        files={"file": ("alunos.csv", csv_content, "text/csv")},
        params={"auto_score": "false"},
    )
    assert resp.status_code == 201

    resp_a = await client.get("/api/v1/students", headers={"X-API-Key": key_a})
    resp_b = await client.get("/api/v1/students", headers={"X-API-Key": key_b})
    assert resp_a.json()["count"] == 1
    assert resp_b.json()["count"] == 0


async def test_require_tenant_match_rejects_mismatched_slug(client, tenant):
    _t, raw_key = tenant
    resp = await client.get(
        "/api/v1/tenants/some-other-tenant/learning",
        headers={"X-API-Key": raw_key},
    )
    assert resp.status_code == 403


async def test_create_tenant_in_non_development_requires_admin_secret(client, monkeypatch):
    import app.api.outcomes as outcomes_module
    settings = outcomes_module.get_settings()
    monkeypatch.setattr(settings, "app_env", "production")

    resp = await client.post("/api/v1/tenants", json={"slug": "newco", "name": "New Co"})
    assert resp.status_code == 403

    resp_ok = await client.post(
        "/api/v1/tenants",
        json={"slug": "newco", "name": "New Co"},
        headers={"X-Admin-Secret": settings.secret_key},
    )
    assert resp_ok.status_code == 201


async def test_create_tenant_rejects_invalid_slug(client):
    resp = await client.post("/api/v1/tenants", json={"slug": "../../etc", "name": "Bad"})
    assert resp.status_code == 422
