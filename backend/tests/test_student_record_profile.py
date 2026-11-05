"""Student record must return only persisted, tenant-scoped attributes.

Financial balances are summaries, not transaction/payment evidence.
"""


async def test_student_record_requires_auth(client):
    response = await client.get("/api/v1/students/00000000-0000-0000-0000-000000000001/risk")
    assert response.status_code == 401


async def test_student_record_exposes_persisted_academic_fields(client, auth_headers):
    csv_content = (
        "matricula,nome,curso,campus,status_aluno,turma,semestre,"
        "presenca_percentual,nota_media,reprovacoes,dias_atraso_boleto,"
        "saldo_devedor,status_financeiro\\n"
        "ST-PROFILE-1,Aluno Perfil,Administração,Centro,ATIVO,T-2026,3,"
        "83,7.5,1,20,420,VENCIDO\\n"
    ).encode("utf-8")
    upload = await client.post(
        "/api/v1/upload", headers=auth_headers,
        files={"file": ("student-profile.csv", csv_content, "text/csv")},
    )
    assert upload.status_code in (200, 201), upload.text

    # Read back the tenant's actual student identifier, never infer an ID from matrícula.
    students = await client.get("/api/v1/students", headers=auth_headers)
    assert students.status_code == 200, students.text
    body = students.json()
    rows = body.get("students", []) if isinstance(body, dict) else body
    match = next((row for row in rows if row.get("matricula") == "ST-PROFILE-1"), None)
    assert match is not None
    profile = await client.get(f"/api/v1/students/{match['id']}/risk", headers=auth_headers)
    assert profile.status_code == 200, profile.text
    data = profile.json()
    assert data["matricula"] == "ST-PROFILE-1"
    for key in (
        "campus", "status_aluno", "turma", "forma_ingresso",
        "presenca_percentual", "nota_media", "reprovacoes",
        "saldo_devedor", "status_financeiro",
    ):
        assert key in data
    assert data["nome"] == "Aluno Perfil"
