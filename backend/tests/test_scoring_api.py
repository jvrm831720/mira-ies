"""Testes de integracao: motor preditivo (predict, score batch, regras de acesso)."""


async def test_predict_requires_auth(client):
    resp = await client.post("/api/v1/predict", json={"matricula": "1", "nome": "X"})
    assert resp.status_code == 401


async def test_predict_returns_risk_score(client, auth_headers):
    resp = await client.post(
        "/api/v1/predict",
        headers=auth_headers,
        json={
            "matricula": "1", "nome": "Risco Alto",
            "dias_atraso_boleto": 45, "recorrencia_atrasos": 3, "dias_sem_login": 30,
            "presenca_percentual": 40.0, "nota_media": 3.0, "reprovacoes": 2, "semestre": 1,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert 0 <= body["risk_score"] <= 100
    assert body["risk_level"] == "critico"
    assert "shap_top_factors" in body


async def test_predict_rejects_out_of_range_presenca(client, auth_headers):
    resp = await client.post(
        "/api/v1/predict",
        headers=auth_headers,
        json={"matricula": "1", "nome": "X", "presenca_percentual": 150.0},
    )
    assert resp.status_code == 422


async def test_predict_rejects_negative_dias_atraso(client, auth_headers):
    resp = await client.post(
        "/api/v1/predict",
        headers=auth_headers,
        json={"matricula": "1", "nome": "X", "dias_atraso_boleto": -5},
    )
    assert resp.status_code == 422


async def test_predict_what_if_quitar_boleto_reduces_risk(client, auth_headers):
    resp = await client.post(
        "/api/v1/predict/what-if",
        headers=auth_headers,
        json={
            "matricula": "1", "nome": "X",
            "dias_atraso_boleto": 30, "recorrencia_atrasos": 2, "dias_sem_login": 5,
            "presenca_percentual": 90.0, "nota_media": 7.0, "reprovacoes": 0, "semestre": 3,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["scenarios"]) == 1
    assert body["scenarios"][0]["delta"] <= 0


async def test_model_info_is_public_and_discloses_synthetic_training(client):
    resp = await client.get("/api/v1/model/info")
    assert resp.status_code == 200
    assert "sintét" in resp.json()["disclaimer"].lower()


async def test_feature_importance_requires_auth(client):
    resp = await client.get("/api/v1/model/feature-importance")
    assert resp.status_code == 401


async def test_feature_importance_with_auth(client, auth_headers):
    resp = await client.get("/api/v1/model/feature-importance", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()["features"]) > 0


async def test_model_train_blocked_until_global_lifecycle_exists(client, auth_headers):
    resp = await client.post("/api/v1/model/train", headers=auth_headers, params={"n_samples": 500})
    assert resp.status_code == 409
    assert "aprovação explícita" in resp.json()["detail"]


async def test_risk_summary_and_critical_list_scoped_to_tenant(client, auth_headers):
    csv_content = (
        b"matricula,nome,dias_atraso_boleto,recorrencia_atrasos,dias_sem_login,presenca_percentual,nota_media,reprovacoes,semestre\n"
        b"ST010,Critico,50,3,40,30.0,2.0,2,1\n"
    )
    await client.post(
        "/api/v1/upload", headers=auth_headers,
        files={"file": ("alunos.csv", csv_content, "text/csv")},
    )
    resp = await client.get("/api/v1/risk/summary", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["summary"]["critico"] >= 1

    resp_critical = await client.get("/api/v1/risk/critical", headers=auth_headers)
    assert resp_critical.status_code == 200
    assert any(s["matricula"] == "ST010" for s in resp_critical.json()["students"])
