"""Validação do importador individual com fixtures sintéticas inspiradas na SophiA.

Os fixtures não são exportações reais nem evidência de homologação do ERP.
"""

from io import BytesIO
from pathlib import Path

import pandas as pd
import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "sophia"


def _fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


@pytest.mark.asyncio
async def test_sophia_synthetic_csv_preview_handles_bom_delimiter_decimals_and_ids(
    client, auth_headers
):
    response = await client.post(
        "/api/v1/upload/preview",
        headers=auth_headers,
        files={
            "file": (
                "sophia_alunos_sintetico.csv",
                _fixture("sophia_alunos_sintetico.csv"),
                "text/csv",
            )
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["can_import"] is True
    assert body["rows_received"] == 2
    assert body["rows_to_import"] == 2
    assert body["mapped_columns"]["matricula"] == "matricula"
    assert body["mapped_columns"]["saldo_devedor"] == "saldo_devedor"
    assert body["mapped_columns"]["frequencia"] == "presenca_percentual"
    rows = {row["matricula"]: row for row in body["sample_rows"]}
    assert "001234" in rows
    assert rows["001234"]["semestre"] == 3
    assert rows["001234"]["saldo_devedor"] == pytest.approx(1234.56)
    assert rows["001234"]["presenca_percentual"] == pytest.approx(82.5)
    assert rows["001234"]["nota_media"] == pytest.approx(7.5)
    assert rows["000078"]["saldo_devedor"] == pytest.approx(0.0)
    assert rows["000078"]["presenca_percentual"] is None
    assert rows["000078"]["nota_media"] is None

    # A prévia é somente leitura: não deve criar estudantes.
    students = await client.get("/api/v1/students", headers=auth_headers)
    assert students.status_code == 200
    assert all(
        item["matricula"] not in {"001234", "000078"}
        for item in students.json()["students"]
    )


@pytest.mark.asyncio
async def test_sophia_synthetic_academic_preview_does_not_turn_minus_one_into_zero(
    client, auth_headers
):
    response = await client.post(
        "/api/v1/upload/preview",
        headers=auth_headers,
        files={
            "file": (
                "sophia_academico_sintetico.csv",
                _fixture("sophia_academico_sintetico.csv"),
                "text/csv",
            )
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    rows = {row["matricula"]: row for row in body["sample_rows"]}
    assert rows["001234"]["nota_media"] is None
    assert rows["000078"]["nota_media"] == pytest.approx(8.75)
    assert any("sentinela" in warning.lower() for warning in body["warnings"])


@pytest.mark.asyncio
async def test_sophia_synthetic_xlsx_multisheet_structure_and_selected_sheet_preview(
    client, auth_headers
):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.DataFrame({"Relatório": ["Dados sintéticos para teste"]}).to_excel(
            writer, sheet_name="Capa", index=False
        )
        pd.DataFrame(
            {
                "Matrícula": ["000321", "000654"],
                "Nome completo": ["Carla Teste", "Diego Teste"],
                "Curso": ["Pedagogia", "Sistemas"],
                "Média geral": ["6,5", "9,0"],
                "Frequência": ["75,0", "98,5"],
            }
        ).to_excel(writer, sheet_name="Alunos", index=False)
    payload = output.getvalue()

    structure = await client.post(
        "/api/v1/upload/structure",
        headers=auth_headers,
        files={"file": ("sophia_sintetico.xlsx", payload, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert structure.status_code == 200, structure.text
    structure_body = structure.json()
    assert {sheet["name"] for sheet in structure_body["sheets"]} == {"Capa", "Alunos"}
    assert structure_body["suggested_sheet"] == "Alunos"

    preview = await client.post(
        "/api/v1/upload/preview",
        headers=auth_headers,
        data={"sheet_name": "Alunos"},
        files={"file": ("sophia_sintetico.xlsx", payload, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert preview.status_code == 200, preview.text
    rows = {row["matricula"]: row for row in preview.json()["sample_rows"]}
    assert rows["000321"]["nota_media"] == pytest.approx(6.5)
    assert rows["000654"]["presenca_percentual"] == pytest.approx(98.5)


def test_generic_subject_grade_header_is_not_assumed_to_be_student_average():
    # O relatório por disciplina pode trazer "Nota" individual. Sem contexto
    # de agregação, esse cabeçalho não deve virar nota_media automaticamente.
    frame = pd.DataFrame(
        {"Matrícula": ["000111"], "Nome": ["Eva Teste"], "Disciplina": ["Matemática"], "Nota": ["9,0"]}
    )
    from app.services.ingestion import normalize_columns

    _, mapping = normalize_columns(frame)
    assert mapping["matricula"] == "matricula"
    assert mapping["nome"] == "nome"
    assert mapping.get("nota") is None
