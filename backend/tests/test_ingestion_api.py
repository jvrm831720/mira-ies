"""Testes de integracao: ingestao via conectores/API (generico + webhooks com HMAC)."""
import hashlib
import hmac
import json


def _sign(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


async def test_catalog_connectors_is_public(client):
    resp = await client.get("/api/v1/connectors")
    assert resp.status_code == 200
    assert resp.json()["count"] > 0


async def test_connector_detail_404_for_unknown(client):
    resp = await client.get("/api/v1/connectors/does-not-exist")
    assert resp.status_code == 404


async def test_generic_ingest_students_requires_auth(client):
    resp = await client.post("/api/v1/ingest/students", json={"students": [{"matricula": "1", "nome": "X"}]})
    assert resp.status_code == 401


async def test_generic_ingest_students_persists(client, auth_headers):
    resp = await client.post(
        "/api/v1/ingest/students",
        headers=auth_headers,
        json={"students": [{"matricula": "G1", "nome": "Gabriel", "attendance": 88}], "auto_score": False},
    )
    assert resp.status_code == 201


async def test_generic_ingest_caps_payload_size(client, auth_headers):
    too_many = [{"matricula": str(i), "nome": f"Aluno {i}"} for i in range(5001)]
    resp = await client.post(
        "/api/v1/ingest/students",
        headers=auth_headers,
        json={"students": too_many},
    )
    assert resp.status_code == 422


async def test_ingest_by_connector_jacad(client, auth_headers):
    resp = await client.post(
        "/api/v1/connectors/jacad/students",
        headers=auth_headers,
        json=[{"codigoAluno": "J1", "nomeAluno": "Julia", "frequencia": 92}],
    )
    assert resp.status_code == 201


async def test_webhook_moodle_rejects_missing_signature_when_secret_configured(client, tenant_factory):
    _t, raw_key = await tenant_factory(slug="moodle-co", name="Moodle Co", webhook_secret="s3cr3t")
    payload = {"id": "M1", "fullname": "Webhook Student", "lastaccess": 0}
    resp = await client.post(
        "/api/v1/webhooks/moodle",
        headers={"X-API-Key": raw_key},
        content=json.dumps(payload),
    )
    assert resp.status_code == 401


async def test_webhook_moodle_accepts_valid_signature(client, tenant_factory):
    secret = "s3cr3t"
    _t, raw_key = await tenant_factory(slug="moodle-co2", name="Moodle Co 2", webhook_secret=secret)
    payload = {"id": "M2", "fullname": "Webhook Student 2", "lastaccess": 0}
    body = json.dumps(payload).encode("utf-8")
    resp = await client.post(
        "/api/v1/webhooks/moodle",
        headers={"X-API-Key": raw_key, "X-Beacon-Signature": f"sha256={_sign(body, secret)}"},
        content=body,
    )
    assert resp.status_code == 201


async def test_webhook_erp_rejects_unsupported_connector(client, auth_headers):
    resp = await client.post(
        "/api/v1/webhooks/erp/unknown-system",
        headers=auth_headers,
        content=json.dumps([{"id": "1"}]),
    )
    assert resp.status_code == 404



async def test_webhook_rejects_unsigned_payload_in_production_even_when_flag_enabled(
    client, tenant_factory, monkeypatch,
):
    from types import SimpleNamespace
    import app.core.security as security
    from app.core.config import get_settings

    current_settings = get_settings()
    _tenant, raw_key = await tenant_factory(
        slug="unsigned-prod", name="Unsigned Production", webhook_secret=None
    )
    monkeypatch.setattr(
        security, "get_settings",
        lambda: SimpleNamespace(
            app_env="production",
            allow_unsigned_webhooks=True,
            secret_key=current_settings.secret_key,
        ),
    )
    resp = await client.post(
        "/api/v1/webhooks/moodle",
        headers={"X-API-Key": raw_key},
        content=json.dumps({"id": "M-PROD", "fullname": "Unsigned"}),
    )
    assert resp.status_code == 401


async def test_ingestion_internal_exception_is_not_returned_to_client(
    client, auth_headers, monkeypatch,
):
    import app.api.connectors as connectors_api

    async def fail_with_sensitive_detail(*args, **kwargs):
        raise RuntimeError("https://internal.example/?token=secret-value")

    monkeypatch.setattr(connectors_api, "ingest_records", fail_with_sensitive_detail)
    resp = await client.post(
        "/api/v1/connectors/jacad/students",
        headers=auth_headers,
        json=[{"codigoAluno": "J-ERR", "nomeAluno": "Julia", "frequencia": 92}],
    )
    assert resp.status_code == 500
    assert resp.json()["detail"] == "Falha interna ao processar ingestao"
    assert "secret-value" not in resp.text
