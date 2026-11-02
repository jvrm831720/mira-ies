from datetime import date
from types import SimpleNamespace

import httpx
import pytest

from app.services.connectors.sponte_api import SponteApiClient
from app.services.connectors.sponte_mapping import build_student_payloads, compact_row, record_id


@pytest.mark.asyncio
async def test_sponte_api_client_uses_key_client_code_and_incremental_pagination():
    calls = []

    def handler(request: httpx.Request):
        calls.append(request)
        page = int(request.url.params["PageNumber"])
        return httpx.Response(200, json={
            "currentPage": page,
            "totalPages": 2,
            "pageSize": 1,
            "totalCount": 2,
            "hasNext": page < 2,
            "items": [{"AlunoID": str(page), "Nome": f"Aluno {page}"}],
        })

    client = SponteApiClient(
        "test-api-key", 77, transport=httpx.MockTransport(handler)
    )
    try:
        rows = await client.fetch_all(
            "alunos", extraction_date=date(2025, 1, 1), page_size=1
        )
    finally:
        await client.close()

    assert len(rows) == 2
    assert calls[0].headers["x-api-key"] == "test-api-key"
    assert calls[0].url.params["CodCliSponte"] == "77"
    assert calls[0].url.params["DataExtracao"] == "2025-01-01"
    assert calls[1].url.params["PageNumber"] == "2"


@pytest.mark.asyncio
async def test_sponte_api_client_caps_page_size_and_rejects_unknown_endpoint():
    calls = []

    def handler(request: httpx.Request):
        calls.append(request)
        return httpx.Response(200, json={"items": [], "totalPages": 1, "hasNext": False})

    client = SponteApiClient("key", 10, transport=httpx.MockTransport(handler))
    try:
        await client.fetch_page("alunos", extraction_date=date.today(), page_size=5000)
        with pytest.raises(ValueError):
            await client.fetch_page("https://evil.example", extraction_date=date.today())
    finally:
        await client.close()

    assert calls[0].url.params["PageSize"] == "1000"


def test_sponte_compaction_uses_provider_ids_and_marks_excluded_rows():
    row = {
        "AlunoID": 10, "ContratoID": 20, "contaReceberID": 30,
        "Situacao": "Pendente", "DataVencimentoParcela": "2026-10-20",
        "ValorTotalParcela": 100, "ValorPagoParcela": 20, "Excluido": 0,
    }
    compact = compact_row("contasreceber", row)
    assert compact["aluno_id"] == "10"
    assert compact["contrato_id"] == 20
    assert compact["situacao"] == "Pendente"
    assert record_id("contasreceber", row) == "30"


def test_sponte_mapping_derives_finance_and_latest_attendance_without_global_grade_average():
    student = SimpleNamespace(
        matricula="101", nome="Ana", curso=None, turma=None, email=None, telefone=None,
        raw_data={
            "sponte": {
                "profile": {"nome": "Ana", "situacao_aluno": "Ativo", "email": "ana@example.com"},
                "contratos": {"20": {"aluno_id": "101", "contrato_id": 20, "curso": "Direito", "turma": "D1"}},
                "contasreceber": {
                    "a": {"aluno_id": "101", "situacao": "Pendente", "data_vencimento": "2026-10-20", "valor_total": 100, "valor_pago": 20},
                    "b": {"aluno_id": "101", "situacao": "Pendente", "data_vencimento": "2026-11-05", "valor_total": 50, "valor_pago": 0},
                    "c": {"aluno_id": "101", "situacao": "Pago", "data_vencimento": "2026-09-01", "valor_total": 80, "valor_pago": 80},
                    "d": {"aluno_id": "101", "situacao": "Pendente", "data_vencimento": "2026-10-01", "valor_total": 90, "valor_pago": 0, "excluido": True},
                },
                "fatofrequenciaalunosativos": {
                    "old": {"aluno_id": "101", "data_extracao": "2026-10-25", "aulas_assistidas": 5, "aulas_totais": 10},
                    "new": {"aluno_id": "101", "data_extracao": "2026-11-01", "aulas_assistidas": 8, "aulas_totais": 10},
                },
                "notas": {
                    "n1": {"aluno_id": "101", "ano": 2026, "semestre": 1, "media": 8.5},
                    "n2": {"aluno_id": "101", "ano": 2026, "semestre": 2, "media": 7.5},
                },
            }
        },
    )
    [payload] = build_student_payloads([student], as_of=date(2026, 11, 2))
    assert payload["DiasAtraso"] == 13
    assert payload["QtdAtrasos"] == 1
    assert payload["SaldoDevedor"] == 130
    assert payload["StatusFinanceiro"] == "VENCIDO"
    assert payload["Frequencia"] == 80
    assert payload["Semestre"] == 2
    assert payload["SituacaoAluno"] == "Ativo"
    assert payload.get("Media") is None


def test_sponte_mapping_does_not_infer_balance_when_payment_amount_is_missing():
    student = SimpleNamespace(
        matricula="102", nome="Bia", curso=None, turma=None, email=None, telefone=None,
        raw_data={"sponte": {
            "profile": {"nome": "Bia"},
            "contasreceber": {
                "a": {"aluno_id": "102", "situacao": "Pendente", "data_vencimento": "2026-11-05", "valor_total": 100}
            },
        }},
    )
    [payload] = build_student_payloads([student], as_of=date(2026, 11, 2))
    assert payload["StatusFinanceiro"] == "EM_ABERTO"
    assert payload["SaldoDevedor"] is None


def test_sponte_mapping_keeps_overdue_unknown_when_pending_due_date_is_missing():
    student = SimpleNamespace(
        matricula="103", nome="Caio", curso=None, turma=None, email=None, telefone=None,
        raw_data={"sponte": {
            "profile": {"nome": "Caio"},
            "contasreceber": {
                "a": {"aluno_id": "103", "situacao": "Pendente", "valor_total": 100, "valor_pago": 0}
            },
        }},
    )
    [payload] = build_student_payloads([student], as_of=date(2026, 11, 2))
    assert payload["StatusFinanceiro"] is None
    assert payload["DiasAtraso"] is None
    assert payload["QtdAtrasos"] is None


def test_sponte_mapping_does_not_treat_unknown_receivable_status_as_paid():
    student = SimpleNamespace(
        matricula="104", nome="Davi", curso=None, turma=None, email=None, telefone=None,
        raw_data={"sponte": {
            "profile": {"nome": "Davi"},
            "contasreceber": {
                "a": {"aluno_id": "104", "situacao": "Em negociação", "valor_total": 100, "valor_pago": 0}
            },
        }},
    )
    [payload] = build_student_payloads([student], as_of=date(2026, 11, 2))
    assert payload["StatusFinanceiro"] is None
    assert payload["SaldoDevedor"] is None
    assert payload["DiasAtraso"] is None
