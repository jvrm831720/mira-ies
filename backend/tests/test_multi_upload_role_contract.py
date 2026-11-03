"""Contrato único de papéis para prévia e confirmação de importação multi-arquivo."""

import pytest


def _files_for_canonical_roles():
    return [
        ("files", ("cadastro.csv", b"matricula,nome,email\nROLE001,Ana Teste,ana@example.test\n", "text/csv")),
        ("files", ("financeiro.csv", b"matricula,dias_atraso_boleto,saldo_devedor,status_financeiro\nROLE001,12,350.50,Em atraso\n", "text/csv")),
        ("files", ("academico.csv", b"matricula,curso,campus\nROLE001,Administracao,Centro\n", "text/csv")),
        ("files", ("historico.csv", b"matricula,dias_sem_login,presenca_percentual,nota_media,reprovacoes\nROLE001,8,82,7.5,1\n", "text/csv")),
        ("files", ("matriculas.csv", b"matricula,turma,semestre,forma_ingresso,status_aluno\nROLE001,ADM-2026-1,3,Transferencia,Ativo\n", "text/csv")),
    ]


@pytest.mark.asyncio
async def test_preview_accepts_all_roles_exposed_by_import_wizard(client, auth_headers):
    roles = ["cadastro", "financeiro", "academico", "historico", "matriculas"]
    response = await client.post(
        "/api/v1/upload/preview-multiple",
        headers=auth_headers,
        files=_files_for_canonical_roles(),
        data={"file_roles": roles},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["summary"]["files_received"] == 5
    assert body["summary"]["files_valid"] == 5
    assert body["persisted"] is False
    assert [item["role"] for item in body["items"]] == roles
    assert body["summary"]["cross_file_conflicts"] == 0
    assert body["consolidated_preview"][0]["matricula"] == "ROLE001"


@pytest.mark.asyncio
async def test_confirmation_uses_same_role_contract_and_persists_merged_student(client, auth_headers):
    roles = ["cadastro", "financeiro", "academico", "historico", "matriculas"]
    response = await client.post(
        "/api/v1/upload/confirm-multiple",
        headers={**auth_headers, "Idempotency-Key": "multi-role-contract-canonical-001"},
        files=_files_for_canonical_roles(),
        data={"file_roles": roles},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["persisted"] is True
    assert body["idempotent_replay"] is False
    assert body["students_imported"] == 1

    students_response = await client.get("/api/v1/students", headers=auth_headers)
    assert students_response.status_code == 200
    student = next(item for item in students_response.json()["students"] if item["matricula"] == "ROLE001")
    assert student["nome"] == "Ana Teste"
    assert student["curso"] == "Administracao"
    assert student["turma"] == "ADM-2026-1"
    assert student["semestre"] == 3
    assert student["dias_atraso_boleto"] == 12
    assert student["saldo_devedor"] == 350.5
    assert student["dias_sem_login"] == 8
    assert student["presenca_percentual"] == 82
    assert student["nota_media"] == 7.5

    replay = await client.post(
        "/api/v1/upload/confirm-multiple",
        headers={**auth_headers, "Idempotency-Key": "multi-role-contract-canonical-001"},
        files=_files_for_canonical_roles(),
        data={"file_roles": roles},
    )
    assert replay.status_code == 201, replay.text
    assert replay.json()["idempotent_replay"] is True
    assert replay.json()["students_imported"] == 1


@pytest.mark.asyncio
async def test_legacy_role_aliases_are_consistent_between_preview_and_confirmation(client, auth_headers):
    roles = ["alunos", "cursos", "engajamento", "desempenho"]
    files = [
        ("files", ("alunos.csv", b"matricula,nome,email\nLEGACY001,Bruno Teste,bruno@example.test\n", "text/csv")),
        ("files", ("cursos.csv", b"matricula,curso\nLEGACY001,Direito\n", "text/csv")),
        ("files", ("engajamento.csv", b"matricula,dias_sem_login,presenca_percentual\nLEGACY001,4,91\n", "text/csv")),
        ("files", ("desempenho.csv", b"matricula,nota_media,reprovacoes\nLEGACY001,8,0\n", "text/csv")),
    ]
    preview = await client.post(
        "/api/v1/upload/preview-multiple",
        headers=auth_headers,
        files=files,
        data={"file_roles": roles},
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["summary"]["files_valid"] == 4
    assert [item["role"] for item in preview.json()["items"]] == roles

    confirmation = await client.post(
        "/api/v1/upload/confirm-multiple",
        headers={**auth_headers, "Idempotency-Key": "multi-role-contract-legacy-001"},
        files=files,
        data={"file_roles": roles},
    )
    assert confirmation.status_code == 201, confirmation.text
    assert confirmation.json()["students_imported"] == 1


@pytest.mark.asyncio
async def test_unknown_role_is_blocked_by_preview_and_confirmation(client, auth_headers):
    files = [("files", ("unknown.csv", b"matricula,nome\nUNKNOWN001,Teste\n", "text/csv"))]
    preview = await client.post(
        "/api/v1/upload/preview-multiple",
        headers=auth_headers,
        files=files,
        data={"file_roles": ["historico_inexistente"]},
    )
    assert preview.status_code == 200
    assert preview.json()["items"][0]["valid"] is False
    assert "Tipo de base desconhecido" in preview.json()["items"][0]["error"]

    confirmation = await client.post(
        "/api/v1/upload/confirm-multiple",
        headers={**auth_headers, "Idempotency-Key": "multi-role-contract-unknown-001"},
        files=files,
        data={"file_roles": ["historico_inexistente"]},
    )
    assert confirmation.status_code == 422
