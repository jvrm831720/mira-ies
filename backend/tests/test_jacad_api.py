from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from app.services.connectors.erp import JacadConnector
from app.services.connectors.jacad_api import (
    JacadApiClient,
    JacadConnectionError,
    decrypt_api_token,
    encrypt_api_token,
    validate_jacad_base_url,
)


def test_jacad_base_url_requires_official_https_origin():
    assert validate_jacad_base_url("https://ies-demo.jacad.com.br/") == "https://ies-demo.jacad.com.br"
    with pytest.raises(ValueError):
        validate_jacad_base_url("http://ies-demo.jacad.com.br")
    with pytest.raises(ValueError):
        validate_jacad_base_url("https://example.com")
    with pytest.raises(ValueError):
        validate_jacad_base_url("https://127.0.0.1")


def test_jacad_credential_encryption_roundtrip(monkeypatch):
    import app.services.connectors.jacad_api as module

    monkeypatch.setattr(module, "get_settings", lambda: SimpleNamespace(secret_key="test-secret-key-for-jacad-encryption"))
    encrypted = encrypt_api_token("token-123")
    assert encrypted != "token-123"
    assert decrypt_api_token(encrypted) == "token-123"


def test_jacad_native_student_payload_maps_ra_and_identity_fields():
    records = JacadConnector().transform({
        "elements": [
            {
                "idAluno": 901,
                "ra": "RA-2026-001",
                "nome": "Ana Silva",
                "email": "ana@example.edu.br",
                "dataAlteracao": "2026-10-31T10:00:00Z",
            },
            {"idAluno": 902, "nome": "Aluno sem RA"},
            {"idAluno": 903, "ra": "RA-003", "nome": ""},
        ]
    })
    assert len(records) == 2
    assert records[0]["matricula"] == "RA-2026-001"
    assert records[0]["nome"] == "Ana Silva"
    assert records[0]["email"] == "ana@example.edu.br"
    assert records[0]["dias_sem_login"] is None
    assert records[0]["presenca_percentual"] is None
    assert records[0]["nota_media"] is None
    assert records[0]["reprovacoes"] is None
    assert records[1]["matricula"] == "902"


@pytest.mark.asyncio
async def test_jacad_api_client_authenticates_and_follows_cursor_pages():
    seen = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/api/v1/auth/token":
            assert request.headers["token"] == "access-token"
            return httpx.Response(200, json={"token": "jwt-session", "expiresIn": 3600})
        assert request.headers["authorization"] == "Bearer jwt-session"
        assert request.url.path == "/api/v2/academico/alunos"
        if request.url.params.get("idCursor") == "200":
            return httpx.Response(200, json={"page": {"idCursorProximo": 0}, "elements": [{"idAluno": 2}]})
        return httpx.Response(200, json={"page": {"idCursor": 0, "idCursorProximo": 200}, "elements": [{"idAluno": 1}]})

    client = JacadApiClient(
        "https://ies-demo.jacad.com.br",
        "access-token",
        transport=httpx.MockTransport(handler),
    )
    try:
        rows = await client.fetch_students(page_size=100)
    finally:
        await client.close()

    assert [row["idAluno"] for row in rows] == [1, 2]
    student_requests = [request for request in seen if request.url.path.endswith("/alunos")]
    assert len(student_requests) == 2
    assert student_requests[0].url.params["pageSize"] == "100"
    assert student_requests[0].url.params["idCursor"] == "0"
    assert student_requests[1].url.params["idCursor"] == "200"


@pytest.mark.asyncio
async def test_jacad_api_client_stops_on_repeated_cursor():
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/auth/token":
            return httpx.Response(200, json={"token": "jwt-session"})
        return httpx.Response(200, json={"page": {"idCursorProximo": 7}, "elements": [{"idAluno": 1}]})

    client = JacadApiClient("https://ies-demo.jacad.com.br", "access-token", transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(JacadConnectionError, match="Cursor JACAD repetido"):
            await client.fetch_students(page_size=1)
    finally:
        await client.close()



def test_jacad_mapping_enriches_enrollment_and_financial_status_without_guessing_history():
    from datetime import date
    from app.services.connectors.jacad_mapping import enrich_jacad_students

    students = [{"idAluno": 10, "ra": "RA-10", "nome": "Ana"}]
    enrollments = [{
        "idMatricula": 100, "idAluno": 10, "ra": "RA-10",
        "status": "ATIVA", "curso": "Administração", "turma": "ADM-2026",
        "idPeriodoLetivo": 20262, "periodoLetivo": "2026.2",
        "idCursoBase": 55, "idCursoMatriz": 56, "matriz": "Matriz 2026",
        "idTurma": 77, "idUnidadeFisica": 3, "unidadeFisica": "Campus Centro",
        "idContrato": 900, "contratoEntregue": 1,
    }]
    summaries = [{
        "idMatricula": 100, "idAluno": 10, "ra": "RA-10",
        "situacaoFinanceira": "VENCIDO",
        "dataVencimentoParcela": "2026-10-20T00:00:00",
        "valorParcela": 850.0,
    }]
    enriched, metadata = enrich_jacad_students(
        students, enrollments, summaries, today=date(2026, 10, 30)
    )

    assert enriched[0]["status_aluno"] == "ATIVA"
    assert enriched[0]["curso"] == "Administração"
    assert enriched[0]["turma"] == "ADM-2026"
    assert enriched[0]["status_financeiro"] == "VENCIDO"
    assert enriched[0]["dias_atraso_boleto"] == 10
    assert "recorrencia_atrasos" not in enriched[0]
    assert "saldo_devedor" not in enriched[0]
    assert metadata["RA-10"]["id_aluno"] == "10"
    assert metadata["RA-10"]["matriculas"][0]["periodo_letivo"] == "2026.2"
    assert metadata["RA-10"]["matriculas"][0]["unidade_fisica"] == "Campus Centro"
    assert metadata["RA-10"]["matriculas"][0]["id_contrato"] == 900
    assert metadata["RA-10"]["financial_summaries"][0]["valor_parcela_aberta"] == 850.0


def test_jacad_mapping_marks_non_overdue_and_no_finance_statuses_without_fabricating_balance():
    from datetime import date
    from app.services.connectors.jacad_mapping import enrich_jacad_students

    students = [
        {"idAluno": 10, "ra": "RA-10", "nome": "Ana"},
        {"idAluno": 11, "ra": "RA-11", "nome": "Bia"},
    ]
    summaries = [
        {"idAluno": 10, "situacaoFinanceira": "EM_ABERTO"},
        {"idAluno": 11, "situacaoFinanceira": "SEM_FINANCEIRO"},
    ]
    enriched, _ = enrich_jacad_students(students, [], summaries, today=date(2026, 10, 30))
    by_ra = {row["ra"]: row for row in enriched}
    assert by_ra["RA-10"]["dias_atraso_boleto"] == 0
    assert by_ra["RA-10"]["recorrencia_atrasos"] == 0
    assert "saldo_devedor" not in by_ra["RA-10"]
    assert by_ra["RA-11"]["dias_atraso_boleto"] == 0
    assert by_ra["RA-11"]["recorrencia_atrasos"] == 0
    assert by_ra["RA-11"]["saldo_devedor"] == 0.0


@pytest.mark.asyncio
async def test_jacad_api_client_fetches_enrollment_and_financial_summary_pages():
    seen = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/api/v1/auth/token":
            return httpx.Response(200, json={"token": "jwt-session"})
        if request.url.path == "/api/v2/academico/matriculas":
            assert request.url.params["idOrg"] == "7"
            return httpx.Response(200, json={"page": {"idCursorProximo": 0}, "elements": [{"idMatricula": 1}]})
        if request.url.path == "/api/v2/financeiro/matriculas/resumo-financeiro":
            assert request.url.params["idOrg"] == "7"
            return httpx.Response(200, json={"page": {"idCursorProximo": 0}, "elements": [{"idMatricula": 1, "situacaoFinanceira": "PAGO"}]})
        raise AssertionError(request.url.path)

    client = JacadApiClient("https://ies-demo.jacad.com.br", "access-token", transport=httpx.MockTransport(handler))
    try:
        enrollments = await client.fetch_enrollments(org_id=7)
        summaries = await client.fetch_financial_summaries(org_id=7)
    finally:
        await client.close()

    assert enrollments == [{"idMatricula": 1}]
    assert summaries[0]["situacaoFinanceira"] == "PAGO"
    assert len([request for request in seen if request.url.path == "/api/v1/auth/token"]) == 1



def test_jacad_mapping_ignores_financial_debt_from_non_active_enrollment():
    from app.services.connectors.jacad_mapping import enrich_jacad_students

    students = [{"idAluno": 10, "ra": "RA-10", "nome": "Ana"}]
    enrollments = [
        {"idMatricula": 100, "idAluno": 10, "status": "CANCELADA"},
        {"idMatricula": 200, "idAluno": 10, "status": "ATIVA"},
    ]
    summaries = [
        {"idMatricula": 100, "idAluno": 10, "situacaoFinanceira": "VENCIDO",
         "dataVencimentoParcela": "2026-09-01T00:00:00"},
        {"idMatricula": 200, "idAluno": 10, "situacaoFinanceira": "PAGO"},
    ]
    enriched, metadata = enrich_jacad_students(students, enrollments, summaries)
    assert enriched[0]["status_financeiro"] == "PAGO"
    assert enriched[0]["dias_atraso_boleto"] == 0
    assert metadata["RA-10"]["financial_summaries"][0]["id_matricula"] == 200


@pytest.mark.asyncio
async def test_jacad_academic_discipline_and_assessment_endpoints_are_paginated():
    seen = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/api/v1/auth/token":
            return httpx.Response(200, json={"token": "jwt-session"})
        if request.url.path == "/api/v1/academico/matricula-disciplina":
            assert request.url.params["idMatricula"] == "321"
            assert request.url.params["pageSize"] == "500"
            return httpx.Response(200, json={
                "page": {"currentPage": 1, "totalPages": 1},
                "elements": [{"idMatriculaDisciplina": 11, "mediaFinal": 8.5, "frequencia": 92}],
            })
        if request.url.path == "/api/v1/academico/notas/consultar":
            assert request.url.params["codigoDaTurma"] == "77"
            assert request.url.params["codigoDisciplinaProfessor"] == "88"
            assert request.url.params["pageSize"] == "500"
            return httpx.Response(200, json={
                "page": {"currentPage": 1, "totalPages": 1},
                "elements": [{
                    "ra": "RA-321", "idMatricula": 321, "idMatriculaDisciplina": 11,
                    "mediaMatriculaDisciplina": 8.5,
                    "itensNotas": [{"identificacao": "N1", "notaAvaliacao": 8.5}],
                }],
            })
        raise AssertionError(request.url.path)

    client = JacadApiClient(
        "https://ies-demo.jacad.com.br", "access-token",
        transport=httpx.MockTransport(handler),
    )
    try:
        disciplines = await client.fetch_enrollment_disciplines(321)
        notes = await client.fetch_assessment_notes(77, 88)
    finally:
        await client.close()

    assert disciplines[0]["frequencia"] == 92
    assert notes[0]["itensNotas"][0]["identificacao"] == "N1"
    assert len([r for r in seen if r.url.path == "/api/v1/auth/token"]) == 1


def test_jacad_metadata_deep_merge_preserves_prior_checkpointed_contracts_and_disciplines():
    from app.services.jacad_queue import _deep_merge

    current = {
        "installments_by_contract": {"100": [{"id_transacao": 1}]},
        "academic_disciplines_by_enrollment": {"10": [{"disciplina": "Matemática"}]},
    }
    merged = _deep_merge(current, {
        "installments_by_contract": {"200": [{"id_transacao": 2}]},
        "academic_disciplines_by_enrollment": {"11": [{"disciplina": "História"}]},
    })
    assert set(merged["installments_by_contract"]) == {"100", "200"}
    assert set(merged["academic_disciplines_by_enrollment"]) == {"10", "11"}
