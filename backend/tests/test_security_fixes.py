"""Testes dirigidos as correcoes de seguranca da auditoria."""
import pytest

from app.services.ingestion import validate_and_clean_row
import pandas as pd


def test_ingestion_clamps_absurd_semestre_and_counters():
    row = pd.Series({
        "matricula": "1", "nome": "Teste",
        "semestre": 9999, "dias_atraso_boleto": -50, "dias_sem_login": 999999,
        "recorrencia_atrasos": 10000, "reprovacoes": -3,
    })
    data, _warnings = validate_and_clean_row(row, 0)
    assert data["semestre"] <= 30
    assert data["dias_atraso_boleto"] >= 0
    assert data["dias_sem_login"] <= 3650
    assert data["recorrencia_atrasos"] <= 100
    assert data["reprovacoes"] >= 0


def test_ingestion_truncates_overlong_strings():
    row = pd.Series({"matricula": "X" * 300, "nome": "Y" * 500})
    data, _warnings = validate_and_clean_row(row, 0)
    assert len(data["matricula"]) <= 50
    assert len(data["nome"]) <= 255


async def test_tenant_model_artifact_integrity_checksum_rejects_tampered_file(
    client, auth_headers, tenant, db_session,
):
    from app.ml.tenant_train import load_tenant_model_from_path, invalidate_tenant_cache
    from app.models.tenant import ModelArtifact
    from sqlalchemy import select

    t, _raw_key = tenant
    outcomes = [
        {"matricula": f"TA{i}", "outcome": "evadiu" if i % 3 == 0 else "ativo"} for i in range(30)
    ]
    await client.post("/api/v1/outcomes", headers=auth_headers, json={"tenant_slug": t.slug, "outcomes": outcomes})
    train_resp = await client.post(
        f"/api/v1/tenants/{t.slug}/train", headers=auth_headers,
        params={"force": "true", "force_activate": "true"},
    )
    assert train_resp.status_code == 200
    artifact_id = train_resp.json()["artifact_id"]

    result = await db_session.execute(select(ModelArtifact).where(ModelArtifact.id == artifact_id))
    artifact = result.scalar_one()
    assert artifact.metrics.get("artifact_sha256")

    with open(artifact.storage_path, "ab") as f:
        f.write(b"tampered-bytes")

    invalidate_tenant_cache(t.slug)
    with pytest.raises(ValueError, match="Integridade"):
        load_tenant_model_from_path(
            artifact.storage_path, t.slug, expected_sha256=artifact.metrics["artifact_sha256"],
        )


def test_tenant_slug_path_traversal_is_rejected_at_storage_layer():
    from app.ml.tenant_train import _safe_tenant_dirname

    with pytest.raises(ValueError):
        _safe_tenant_dirname("../../etc")
    with pytest.raises(ValueError):
        _safe_tenant_dirname("")
    assert _safe_tenant_dirname("valid-slug-1") == "valid-slug-1"
