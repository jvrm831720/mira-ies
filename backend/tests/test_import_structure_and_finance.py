"""Regression tests for structural inspection, sheet selection and financial import mapping."""
import io

from openpyxl import Workbook

from app.api.upload import inspect_file_structure, read_file_to_dataframe
from app.services.ingestion import normalize_columns, prepare_import_rows


def _workbook_bytes() -> bytes:
    workbook = Workbook()
    info = workbook.active
    info.title = "LEIA-ME"
    info.append(["MIRA — teste de mapeamento"])
    info.append(["Tipo", "Base limpa"])
    cadastro = workbook.create_sheet("Cadastro")
    cadastro.append(["Matrícula do aluno", "Nome completo", "Curso / programa", "Semestre atual", "E-mail de contato"])
    cadastro.append(["0001842", "Ana Beatriz Souza", "Administração", 3, "ana@example.com"])
    financeiro = workbook.create_sheet("Financeiro")
    financeiro.append(["ID matrícula", "Débito total (R$)", "Qtd. parcelas vencidas", "Status de pagamento"])
    financeiro.append(["0001842", "3.250,00", 3, "Em atraso"])
    stream = io.BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def test_structure_inspection_suggests_cadastro_not_readme_first():
    result = inspect_file_structure(_workbook_bytes(), "xlsx")
    assert result["suggested_sheet"] == "Cadastro"
    assert result["requires_sheet_selection"] is False
    assert next(sheet for sheet in result["sheets"] if sheet["name"] == "LEIA-ME")["required_fields_found"] is False
    cadastro = next(sheet for sheet in result["sheets"] if sheet["name"] == "Cadastro")
    assert cadastro["required_fields_found"] is True
    assert cadastro["columns"][0] == "Matrícula do aluno"


def test_selected_sheet_reader_preserves_leading_zero_matricula():
    df = read_file_to_dataframe(_workbook_bytes(), "xlsx", sheet_name="Cadastro")
    assert df.iloc[0]["Matrícula do aluno"] == "0001842"


def test_aliases_recognize_portuguese_headers_and_financial_fields():
    import pandas as pd

    df = pd.DataFrame([{
        "Matrícula do aluno": "0001842",
        "Nome completo": "Ana Beatriz Souza",
        "Semestre atual": "3",
        "Débito total (R$)": "3.250,00",
        "Qtd. parcelas vencidas": "3",
        "Status de pagamento": "Em atraso",
    }])
    normalized, mapping = normalize_columns(df)
    assert mapping["matricula_do_aluno"] == "matricula"
    assert mapping["nome_completo"] == "nome"
    assert mapping["semestre_atual"] == "semestre"
    assert mapping["debito_total_r"] == "saldo_devedor"
    assert mapping["qtd_parcelas_vencidas"] == "recorrencia_atrasos"
    assert mapping["status_de_pagamento"] == "status_financeiro"
    prepared = prepare_import_rows(df)
    assert prepared["_cleaned_rows"][0]["data"]["matricula"] == "0001842"
    assert prepared["_cleaned_rows"][0]["data"]["saldo_devedor"] == 3250.0
    assert prepared["_cleaned_rows"][0]["data"]["recorrencia_atrasos"] == 3
    assert prepared["_cleaned_rows"][0]["data"]["status_financeiro"] == "Em atraso"


async def test_structure_and_preview_endpoints_allow_selected_sheet(client, tenant):
    _tenant, key = tenant
    content = _workbook_bytes()
    structure = await client.post(
        "/api/v1/upload/structure",
        headers={"X-API-Key": key},
        files={"file": ("base.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert structure.status_code == 200, structure.text
    assert structure.json()["suggested_sheet"] == "Cadastro"
    assert structure.json()["persisted"] is False

    preview = await client.post(
        "/api/v1/upload/preview",
        headers={"X-API-Key": key},
        files={"file": ("base.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"sheet_name": "Cadastro"},
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["can_import"] is True
    assert body["rows_received"] == 1
    assert body["sample_rows"][0]["matricula"] == "0001842"
