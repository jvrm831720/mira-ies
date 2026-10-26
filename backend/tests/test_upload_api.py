"""Testes de integracao: upload de planilhas e protecao contra path traversal."""

from app.api.upload import sanitize_filename, UPLOAD_DIR


def test_sanitize_filename_strips_directory_components():
    assert sanitize_filename("../../etc/passwd") == "passwd"
    assert sanitize_filename("..\\..\\windows\\system32\\evil.csv") == "evil.csv"


def test_sanitize_filename_replaces_dangerous_characters():
    result = sanitize_filename("alunos;rm -rf $(whoami).csv")
    assert "/" not in result and ";" not in result and " " not in result


def test_sanitize_filename_handles_empty():
    assert sanitize_filename("") == "upload"


async def test_upload_rejects_invalid_extension(client, auth_headers):
    resp = await client.post(
        "/api/v1/upload",
        headers=auth_headers,
        files={"file": ("alunos.exe", b"conteudo", "application/octet-stream")},
    )
    assert resp.status_code == 400


async def test_upload_rejects_empty_file(client, auth_headers):
    resp = await client.post(
        "/api/v1/upload",
        headers=auth_headers,
        files={"file": ("alunos.csv", b"", "text/csv")},
    )
    assert resp.status_code == 422


async def test_upload_rejects_missing_required_columns(client, auth_headers):
    csv_content = b"curso,nota\nEngenharia,8.0\n"
    resp = await client.post(
        "/api/v1/upload",
        headers=auth_headers,
        files={"file": ("alunos.csv", csv_content, "text/csv")},
    )
    assert resp.status_code == 422


async def test_upload_happy_path_persists_students(client, auth_headers):
    csv_content = (
        b"matricula,nome,dias_atraso_boleto,dias_sem_login,presenca_percentual,nota_media\n"
        b"ST001,Joao Teste,5,2,95.0,8.0\n"
        b"ST002,Maria Teste,40,30,50.0,3.0\n"
    )
    resp = await client.post(
        "/api/v1/upload",
        headers=auth_headers,
        files={"file": ("alunos.csv", csv_content, "text/csv")},
        params={"auto_score": "true"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["students_imported"] == 2
    assert body["scoring"]["scored"] == 2
    # aluno com atraso/inatividade grave deve ficar com risco mais alto que o saudavel
    students = body["scoring"]["students"]
    by_matricula = {s["matricula"]: s for s in students}
    assert by_matricula["ST002"]["risk_score"] > by_matricula["ST001"]["risk_score"]


async def test_upload_path_traversal_filename_stays_inside_upload_dir(client, auth_headers):
    before = set(UPLOAD_DIR.glob("*"))
    csv_content = b"matricula,nome\n001,Teste\n"
    resp = await client.post(
        "/api/v1/upload",
        headers=auth_headers,
        files={"file": ("../../../tmp/evil.csv", csv_content, "text/csv")},
        params={"auto_score": "false"},
    )
    assert resp.status_code == 201
    after = set(UPLOAD_DIR.glob("*"))
    new_files = after - before
    assert len(new_files) == 1
    created = new_files.pop()
    assert created.resolve().parent == UPLOAD_DIR.resolve()
    assert ".." not in created.name
    created.unlink()


async def test_upload_preserves_leading_zeros_in_matricula(client, auth_headers):
    csv_content = b"matricula,nome\n00123,Zero Lider\n"
    resp = await client.post(
        "/api/v1/upload",
        headers=auth_headers,
        files={"file": ("alunos.csv", csv_content, "text/csv")},
        params={"auto_score": "false"},
    )
    assert resp.status_code == 201
    resp_list = await client.get("/api/v1/students", headers=auth_headers)
    matriculas = [s["matricula"] for s in resp_list.json()["students"]]
    assert "00123" in matriculas


async def test_upload_status_endpoint_isolated_by_tenant(client, tenant_factory):
    _t_a, key_a = await tenant_factory(slug="iso-a", name="Iso A")
    _t_b, key_b = await tenant_factory(slug="iso-b", name="Iso B")
    csv_content = b"matricula,nome\n001,Teste\n"
    resp = await client.post(
        "/api/v1/upload",
        headers={"X-API-Key": key_a},
        files={"file": ("alunos.csv", csv_content, "text/csv")},
        params={"auto_score": "false"},
    )
    batch_id = resp.json()["batch"]["id"]

    resp_other_tenant = await client.get(f"/api/v1/upload/status/{batch_id}", headers={"X-API-Key": key_b})
    assert resp_other_tenant.status_code == 404

    resp_owner = await client.get(f"/api/v1/upload/status/{batch_id}", headers={"X-API-Key": key_a})
    assert resp_owner.status_code == 200


async def test_multi_file_preview_validates_without_persisting(client, auth_headers):
    first = b"matricula,nome,curso\nM001,Ana,Enfermagem\n"
    second = b"matricula,nome,curso\nM002,Bruno,Administracao\n"
    response = await client.post(
        "/api/v1/upload/preview-multiple",
        headers=auth_headers,
        files=[
            ("files", ("alunos.csv", first, "text/csv")),
            ("files", ("cursos.csv", second, "text/csv")),
        ],
        data={"file_roles": ["alunos", "cursos"]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["files_received"] == 2
    assert body["summary"]["files_valid"] == 2
    assert body["persisted"] is False
    assert body["cross_file_relationships_validated"] is True
    assert [item["role"] for item in body["items"]] == ["alunos", "cursos"]


async def test_multi_file_preview_rejects_more_than_ten_files(client, auth_headers):
    files = [
        ("files", (f"base-{index}.csv", b"matricula,nome\n001,Ana\n", "text/csv"))
        for index in range(11)
    ]
    response = await client.post(
        "/api/v1/upload/preview-multiple",
        headers=auth_headers,
        files=files,
    )
    assert response.status_code == 422


def test_import_maps_campus_and_student_status():
    import pandas as pd
    from app.services.ingestion import prepare_import_rows

    frame = pd.DataFrame([{
        "matricula": "0001842",
        "nome": "Ana Beatriz Souza",
        "unidade": "Centro",
        "status_aluno": "Ativo",
    }])
    prepared = prepare_import_rows(frame)
    row = prepared["_cleaned_rows"][0]["data"]

    assert prepared["can_import"] is True
    assert prepared["mapped_columns"]["unidade"] == "campus"
    assert prepared["mapped_columns"]["status_aluno"] == "status_aluno"
    assert row["matricula"] == "0001842"
    assert row["campus"] == "Centro"
    assert row["status_aluno"] == "Ativo"



def test_invalid_status_and_email_are_flagged_without_clean_values():
    import pandas as pd
    from app.services.ingestion import prepare_import_rows

    frame = pd.DataFrame([{
        "matricula": "VAL001",
        "nome": "Pessoa Teste",
        "email": "email-invalido",
        "semestre": "semestre dois",
        "status_aluno": "Talvez",
    }])
    prepared = prepare_import_rows(frame)
    row = prepared["_cleaned_rows"][0]["data"]

    assert row["email"] is None
    assert row["semestre"] is None
    assert row["status_aluno"] is None
    assert any("e-mail inválido" in warning and "valor será ignorado" in warning for warning in prepared["warnings"])
    assert any("status acadêmico" in warning and "preservado" in warning for warning in prepared["warnings"])


def test_duplicate_matricula_with_different_names_blocks_import():
    import pandas as pd
    from app.services.ingestion import prepare_import_rows

    frame = pd.DataFrame([
        {"matricula": "DUP001", "nome": "Ana Souza"},
        {"matricula": "DUP001", "nome": "Felipe Ribeiro"},
    ])
    prepared = prepare_import_rows(frame)

    assert prepared["can_import"] is False
    assert prepared["duplicate_identity_conflicts"]
    assert "nomes diferentes" in prepared["duplicate_identity_conflicts"][0]["message"]


async def test_upload_blocks_existing_matricula_with_different_name(client, auth_headers):
    original = b"matricula,nome,curso\nSAFE001,Ana Souza,Administracao\n"
    first = await client.post(
        "/api/v1/upload",
        headers=auth_headers,
        files={"file": ("original.csv", original, "text/csv")},
        params={"auto_score": "false"},
    )
    assert first.status_code == 201

    conflicting = b"matricula,nome,curso\nSAFE001,Felipe Ribeiro,Direito\n"
    second = await client.post(
        "/api/v1/upload",
        headers=auth_headers,
        files={"file": ("conflicting.csv", conflicting, "text/csv")},
        params={"auto_score": "false"},
    )
    assert second.status_code == 422
    assert "difere do cadastro existente" in second.json()["detail"]

    students = await client.get("/api/v1/students", headers=auth_headers)
    saved = next(s for s in students.json()["students"] if s["matricula"] == "SAFE001")
    assert saved["nome"] == "Ana Souza"


async def test_upload_preserves_existing_fields_when_incoming_values_are_invalid(client, auth_headers):
    original = (
        b"matricula,nome,email,semestre,status_aluno\n"
        b"SAFE002,Camila Alves,camila@example.com,3,Ativo\n"
    )
    first = await client.post(
        "/api/v1/upload",
        headers=auth_headers,
        files={"file": ("original.csv", original, "text/csv")},
        params={"auto_score": "false"},
    )
    assert first.status_code == 201

    invalid_update = (
        b"matricula,nome,email,semestre,status_aluno\n"
        b"SAFE002,Camila Alves,camila@,semestre dois,Talvez\n"
    )
    second = await client.post(
        "/api/v1/upload",
        headers=auth_headers,
        files={"file": ("invalid-update.csv", invalid_update, "text/csv")},
        params={"auto_score": "false"},
    )
    assert second.status_code == 201

    students = await client.get("/api/v1/students", headers=auth_headers)
    saved = next(s for s in students.json()["students"] if s["matricula"] == "SAFE002")
    assert saved["nome"] == "Camila Alves"
    assert saved["semestre"] == 3
