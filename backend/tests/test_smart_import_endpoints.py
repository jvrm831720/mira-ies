"""Integration coverage for Smart Import and custom field permissions."""

import json

import pytest


def _upload(data: bytes) -> dict:
    return {"file": ("students.csv", data, "text/csv")}


def _mapping(mapping: dict[str, str]) -> dict:
    return {"payload": json.dumps({"mapping": mapping, "key_field": "matricula"})}


@pytest.mark.asyncio
async def test_preview_is_dry_run(client, tenant):
    _org, key = tenant
    headers = {"X-API-Key": key}
    preview = await client.post(
        "/api/v1/import/preview",
        headers=headers,
        files=_upload(b"matricula,nome,curso\n001,Ana,Pedagogia\n"),
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["key_stats"]["valid"] == 1
    assert preview.json()["key_header"] == "matricula"
    students = await client.get("/api/v1/students", headers=headers)
    assert students.status_code == 200
    assert students.json()["count"] == 0


@pytest.mark.asyncio
async def test_apply_is_idempotent_and_consent_is_audited(client, tenant):
    _org, key = tenant
    csv = b"matricula,nome,communication_opt_out\n001,Ana,sim\n"
    headers = {"X-API-Key": key, "Idempotency-Key": "smart-one"}
    mapping = {"matricula": "matricula", "nome": "nome",
               "communication_opt_out": "communication_opt_out"}

    first = await client.post(
        "/api/v1/import/apply?auto_score=false", headers=headers,
        files=_upload(csv), data=_mapping(mapping),
    )
    assert first.status_code == 201, first.text
    assert first.json()["created"] == 1

    replay = await client.post(
        "/api/v1/import/apply?auto_score=false", headers=headers,
        files=_upload(csv), data=_mapping(mapping),
    )
    assert replay.status_code == 201, replay.text
    assert replay.json()["idempotent_replay"] is True
    assert replay.json()["created"] == 1

    second = await client.post(
        "/api/v1/import/apply?auto_score=false",
        headers={"X-API-Key": key, "Idempotency-Key": "smart-two"},
        files=_upload(b"matricula,nome,communication_opt_out\n001,Ana Nova,nao\n"),
        data=_mapping(mapping),
    )
    assert second.status_code == 201, second.text
    assert second.json()["updated"] == 1

    students = await client.get("/api/v1/students", headers={"X-API-Key": key})
    assert students.status_code == 200
    records = students.json()["students"]
    assert len(records) == 1
    assert records[0]["communication_opt_out"] is True
    assert records[0]["nome"] == "Ana Nova"
    audit = await client.get(
        f"/api/v1/students/{records[0]['id']}/consent-audit",
        headers={"X-API-Key": key},
    )
    assert audit.status_code == 200
    assert audit.json()["count"] == 1
    assert audit.json()["events"][0]["event_type"] == "global_opt_out_enabled"

    changed_file = await client.post(
        "/api/v1/import/apply?auto_score=false", headers=headers,
        files=_upload(b"matricula,nome\n001,Eva\n"),
        data=_mapping({"matricula": "matricula", "nome": "nome"}),
    )
    assert changed_file.status_code == 409


@pytest.mark.asyncio
async def test_invalid_and_duplicate_rows_are_excluded(client, tenant):
    _org, key = tenant
    reply = await client.post(
        "/api/v1/import/apply?auto_score=false",
        headers={"X-API-Key": key, "Idempotency-Key": "smart-invalid"},
        files=_upload(b"matricula,nome,semestre\n001,Ana,2\n001,Ana,3\n002,Bia,2.5\n"),
        data=_mapping({"matricula": "matricula", "nome": "nome", "semestre": "semestre"}),
    )
    assert reply.status_code == 201, reply.text
    assert reply.json()["created"] == 1
    assert reply.json()["rejected"] == 2
    students = await client.get("/api/v1/students", headers={"X-API-Key": key})
    assert students.json()["count"] == 1


@pytest.mark.asyncio
async def test_no_valid_records_never_create_a_batch(client, tenant):
    _org, key = tenant
    reply = await client.post(
        "/api/v1/import/apply?auto_score=false",
        headers={"X-API-Key": key, "Idempotency-Key": "smart-empty"},
        files=_upload(b"matricula,nome,semestre\n001,Ana,2.5\n"),
        data=_mapping({"matricula": "matricula", "nome": "nome", "semestre": "semestre"}),
    )
    assert reply.status_code == 422, reply.text
    students = await client.get("/api/v1/students", headers={"X-API-Key": key})
    assert students.json()["count"] == 0


@pytest.mark.asyncio
async def test_custom_fields_do_not_cross_tenants(client, tenant_factory):
    _a, key_a = await tenant_factory("smart-a", "Smart A")
    _b, key_b = await tenant_factory("smart-b", "Smart B")
    response = await client.post(
        "/api/v1/custom-fields", headers={"X-API-Key": key_a},
        json={"label": "Polo de apoio", "data_type": "text"},
    )
    assert response.status_code == 201, response.text
    field_id = response.json()["id"]
    own = await client.get("/api/v1/custom-fields", headers={"X-API-Key": key_a})
    other = await client.get("/api/v1/custom-fields", headers={"X-API-Key": key_b})
    assert own.status_code == 200 and len(own.json()["items"]) == 1
    assert other.status_code == 200 and other.json()["items"] == []
    cross = await client.patch(
        f"/api/v1/custom-fields/{field_id}",
        headers={"X-API-Key": key_b}, json={"label": "Alterado"},
    )
    assert cross.status_code == 404


@pytest.mark.asyncio
async def test_smart_import_can_run_scoring_without_inventing_risk(client, tenant, monkeypatch):
    from app.ml import scoring

    _org, key = tenant
    called = []

    async def fake_score(session, batch_id, *, force, tenant_id, tenant_slug):
        called.append((batch_id, force, tenant_id, tenant_slug))
        return {"scored": 0, "indeterminate_count": 1, "summary": {}}

    monkeypatch.setattr(scoring, "score_batch", fake_score)
    reply = await client.post(
        "/api/v1/import/apply",
        headers={"X-API-Key": key, "Idempotency-Key": "smart-scoring"},
        files=_upload(b"matricula,nome\n900,Ana\n"),
        data=_mapping({"matricula": "matricula", "nome": "nome"}),
    )
    assert reply.status_code == 201, reply.text
    assert reply.json()["created"] == 1
    assert reply.json()["scoring"]["scored"] == 0
    assert reply.json()["scoring"]["indeterminate_count"] == 1
    assert len(called) == 1 and called[0][1] is True
