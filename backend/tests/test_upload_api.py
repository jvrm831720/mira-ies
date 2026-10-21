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
