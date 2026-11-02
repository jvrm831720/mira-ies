"""Integration tests for the guided, deterministic smart-import workflow."""
import json

import pytest
from sqlalchemy import select

from app.models.student import Student


def _upload(csv: bytes, name: str = "students.csv"):
    return {"file": (name, csv, "text/csv")}


@pytest.mark.asyncio
async def test_preview_autodetects_common_english_headers_without_persisting(client, tenant):
    tenant_obj, key = tenant
    csv = (
        b"Student ID,Full Name,Email Address,Course Name,Attendance Percentage\n"
        b"00123,Ana Souza,ana@example.edu.br,Nursing,96\n"
        b"00124,Bruno Lima,bruno@example.edu.br,Law,82\n"
    )
    response = await client.post(
        "/api/v1/upload/preview",
        headers={"X-API-Key": key},
        files=_upload(csv),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["can_import"] is True
    assert body["rows_received"] == 2
    assert body["rows_to_import"] == 2
    assert body["mapped_columns"]["student_id"] == "matricula"
    assert body["mapped_columns"]["full_name"] == "nome"
    assert body["mapped_columns"]["email_address"] == "email"
    assert body["mapped_columns"]["course_name"] == "curso"
    assert body["mapped_columns"]["attendance_percentage"] == "presenca_percentual"
    assert body["sample_rows"][0]["matricula"] == "00123"
    assert body["existing_matches"] == 0

    # Prévia nunca cria lote nem aluno.
    batches = (await client.get("/api/v1/upload/expected-columns")).json()
    assert "field_labels" in batches
    students = await client.get("/api/v1/students", headers={"X-API-Key": key})
    assert students.json()["count"] == 0


@pytest.mark.asyncio
async def test_manual_mapping_is_used_by_preview_and_persisted_upload(client, tenant):
    _tenant, key = tenant
    mapping = {"enrollment_code": "matricula", "legal_name": "nome", "major": "curso"}
    csv = b"Enrollment Code,Legal Name,Major\nA-001,Ana Souza,Pedagogia\n"

    preview = await client.post(
        "/api/v1/upload/preview",
        headers={"X-API-Key": key},
        files=_upload(csv),
        data={"column_mapping": json.dumps(mapping)},
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["can_import"] is True
    assert preview.json()["mapped_columns"] == mapping

    upload = await client.post(
        "/api/v1/upload",
        headers={"X-API-Key": key},
        files=_upload(csv),
        data={"column_mapping": json.dumps(mapping)},
        params={"auto_score": "false"},
    )
    assert upload.status_code == 201, upload.text
    assert upload.json()["students_imported"] == 1

    students = (await client.get("/api/v1/students", headers={"X-API-Key": key})).json()["students"]
    assert len(students) == 1
    assert students[0]["matricula"] == "A-001"
    assert students[0]["nome"] == "Ana Souza"
    assert students[0]["curso"] == "Pedagogia"


@pytest.mark.asyncio
async def test_reimport_updates_same_tenant_student_without_erasing_empty_fields(client, tenant, db_session):
    tenant_obj, key = tenant
    first_csv = (
        b"matricula,nome,email,telefone,communication_opt_out\n"
        b"KEEP-001,Nome Antigo,aluno@example.edu.br,11988887777,true\n"
    )
    first = await client.post(
        "/api/v1/upload",
        headers={"X-API-Key": key},
        files=_upload(first_csv, "first.csv"),
        params={"auto_score": "false"},
    )
    assert first.status_code == 201, first.text
    first_student = (
        await db_session.execute(
            select(Student).where(Student.tenant_id == tenant_obj.id, Student.matricula == "KEEP-001")
        )
    ).scalar_one()
    original_id = first_student.id

    # E-mail, telefone e a preferência de opt-out não aparecem no segundo arquivo.
    second_csv = b"matricula,nome,curso\nKEEP-001,Nome Antigo,Direito\n"
    second = await client.post(
        "/api/v1/upload",
        headers={"X-API-Key": key},
        files=_upload(second_csv, "second.csv"),
        params={"auto_score": "false"},
    )
    assert second.status_code == 201, second.text
    quality = second.json()["quality"]
    assert quality["rows_created"] == 0
    assert quality["rows_updated"] == 1
    assert quality["existing_matches"] == 1
    await db_session.refresh(first_student)

    students = list(
        (
            await db_session.execute(
                select(Student).where(Student.tenant_id == tenant_obj.id, Student.matricula == "KEEP-001")
            )
        ).scalars().all()
    )
    assert len(students) == 1
    assert students[0].id == original_id
    assert students[0].nome == "Nome Antigo"
    assert students[0].curso == "Direito"
    assert students[0].email == "aluno@example.edu.br"
    assert students[0].telefone == "11988887777"
    assert students[0].communication_opt_out is True


@pytest.mark.asyncio
async def test_same_matricula_is_never_upserted_across_tenants(client, tenant_factory, db_session):
    tenant_a, key_a = await tenant_factory(slug="smart-import-a")
    tenant_b, key_b = await tenant_factory(slug="smart-import-b")
    csv_a = b"matricula,nome\nSAME-RA,Ana na A\n"
    csv_b = b"matricula,nome\nSAME-RA,Ana na B\n"

    response_a = await client.post(
        "/api/v1/upload", headers={"X-API-Key": key_a},
        files=_upload(csv_a), params={"auto_score": "false"},
    )
    response_b = await client.post(
        "/api/v1/upload", headers={"X-API-Key": key_b},
        files=_upload(csv_b), params={"auto_score": "false"},
    )
    assert response_a.status_code == 201, response_a.text
    assert response_b.status_code == 201, response_b.text
    assert response_a.json()["quality"]["rows_created"] == 1
    assert response_b.json()["quality"]["rows_created"] == 1
    rows = list(
        (
            await db_session.execute(
                select(Student).where(Student.matricula == "SAME-RA")
            )
        ).scalars().all()
    )
    assert len(rows) == 2
    names_by_tenant = {row.tenant_id: row.nome for row in rows}
    assert names_by_tenant[tenant_a.id] == "Ana na A"
    assert names_by_tenant[tenant_b.id] == "Ana na B"


@pytest.mark.asyncio
async def test_preview_flags_bad_rows_duplicate_matriculas_and_invalid_email(client, tenant):
    _tenant, key = tenant
    csv = (
        b"matricula,nome,email,presenca_percentual\n"
        b"DUP-1,Ana,not-an-email,140\n"
        b"DUP-1,Ana Atual,ana@example.edu.br,90\n"
        b"OK-1,Bruno,bruno@example.edu.br,85\n"
        b",Sem Matricula,missing@example.edu.br,80\n"
    )
    response = await client.post(
        "/api/v1/upload/preview", headers={"X-API-Key": key}, files=_upload(csv)
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["rows_received"] == 4
    assert body["rows_to_import"] == 1
    assert body["invalid_rows_count"] == 3
    assert body["duplicates_in_file"] == 0
    assert body["can_import"] is True
    assert any("nomes diferentes" in item["message"] for item in body["invalid_rows"])
    assert any("e-mail inválido" in warning for warning in body["warnings"])
    assert any("limitado" in warning for warning in body["warnings"])
    assert body["sample_rows"][0]["nome"] == "Bruno"


@pytest.mark.asyncio
async def test_upload_imports_valid_rows_and_excludes_all_conflicting_matriculas(client, tenant):
    _tenant, key = tenant
    csv = (
        b"matricula,nome,curso\n"
        b"CONFLICT-1,Ana Souza,Direito\n"
        b"CONFLICT-1,Ana Lima,Medicina\n"
        b"VALID-1,Bruno Lima,Administracao\n"
        b",Sem Matricula,Direito\n"
    )
    response = await client.post(
        "/api/v1/upload",
        headers={"X-API-Key": key},
        files=_upload(csv),
        params={"auto_score": "false"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["quality"]["rows_created"] == 1
    assert body["quality"]["rows_discarded"] == 3
    students = await client.get("/api/v1/students", headers={"X-API-Key": key})
    assert students.status_code == 200
    imported = students.json()["students"]
    assert len(imported) == 1
    assert imported[0]["matricula"] == "VALID-1"


@pytest.mark.asyncio
async def test_preview_rejects_mapping_two_columns_to_same_field(client, tenant):
    _tenant, key = tenant
    csv = b"RA,matricula,nome\n1,1,Ana\n"
    mapping = {"ra": "matricula", "matricula": "matricula", "nome": "nome"}
    response = await client.post(
        "/api/v1/upload/preview",
        headers={"X-API-Key": key},
        files=_upload(csv),
        data={"column_mapping": json.dumps(mapping)},
    )
    assert response.status_code == 422
    assert "Mais de uma coluna" in response.json()["detail"]


@pytest.mark.asyncio
async def test_preview_is_tenant_scoped_for_existing_matches(client, tenant_factory):
    _tenant_a, key_a = await tenant_factory(slug="preview-scope-a")
    _tenant_b, key_b = await tenant_factory(slug="preview-scope-b")
    csv = b"matricula,nome\nLOCAL-1,Ana\n"
    first = await client.post(
        "/api/v1/upload", headers={"X-API-Key": key_a},
        files=_upload(csv), params={"auto_score": "false"},
    )
    assert first.status_code == 201, first.text

    preview_a = await client.post("/api/v1/upload/preview", headers={"X-API-Key": key_a}, files=_upload(csv))
    preview_b = await client.post("/api/v1/upload/preview", headers={"X-API-Key": key_b}, files=_upload(csv))
    assert preview_a.status_code == 200 and preview_a.json()["existing_matches"] == 1
    assert preview_b.status_code == 200 and preview_b.json()["existing_matches"] == 0



@pytest.mark.asyncio
async def test_preview_multiple_accepts_complementary_finance_file_without_name(client, tenant):
    _tenant, key = tenant
    files = [
        ("files", ("cadastro.csv", b"matricula,nome,curso\n00123,Ana Souza,Direito\n", "text/csv")),
        ("files", ("financeiro.csv", b"matricula,dias_atraso_boleto,recorrencia_atrasos\n00123,12,3\n", "text/csv")),
    ]
    response = await client.post(
        "/api/v1/upload/preview-multiple",
        headers={"X-API-Key": key},
        files=files,
        data={"file_roles": ["cadastro", "financeiro"]},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["persisted"] is False
    assert body["cross_file_relationships_validated"] is True
    assert body["summary"]["consolidated_students"] == 1
    assert body["consolidated_preview"][0]["matricula"] == "00123"
    assert body["consolidated_preview"][0]["fields"]["nome"] == "Ana Souza"
    assert body["consolidated_preview"][0]["fields"]["dias_atraso_boleto"] == "12"
    assert body["summary"]["cross_file_conflicts"] == 0
    students = await client.get("/api/v1/students", headers={"X-API-Key": key})
    assert students.json()["count"] == 0


@pytest.mark.asyncio
async def test_preview_multiple_flags_conflicting_values_and_unknown_role(client, tenant):
    _tenant, key = tenant
    files = [
        ("files", ("cadastro.csv", b"matricula,nome,curso\n00123,Ana Souza,Direito\n", "text/csv")),
        ("files", ("outro.csv", b"matricula,nome,curso\n00123,Ana Souza,Medicina\n", "text/csv")),
    ]
    response = await client.post(
        "/api/v1/upload/preview-multiple",
        headers={"X-API-Key": key},
        files=files,
        data={"file_roles": ["cadastro", "cadastro"]},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["summary"]["cross_file_conflicts"] == 1
    assert body["conflicts"][0]["field"] == "curso"
    assert body["consolidated_preview"][0]["requires_review"] is True

    invalid = await client.post(
        "/api/v1/upload/preview-multiple",
        headers={"X-API-Key": key},
        files=[("files", ("financeiro.csv", b"matricula,dias_atraso_boleto\n00123,12\n", "text/csv"))],
        data={"file_roles": ["unknown"]},
    )
    assert invalid.status_code == 200, invalid.text
    assert invalid.json()["items"][0]["valid"] is False


@pytest.mark.asyncio
async def test_confirm_multiple_persists_complementary_bases_in_one_batch(client, tenant):
    _tenant, key = tenant
    files = [
        ("files", ("cadastro.csv", b"matricula,nome,curso\n00123,Ana Souza,Direito\n", "text/csv")),
        ("files", ("financeiro.csv", b"matricula,dias_atraso_boleto,recorrencia_atrasos\n00123,12,3\n", "text/csv")),
    ]
    response = await client.post(
        "/api/v1/upload/confirm-multiple",
        headers={"X-API-Key": key, "Idempotency-Key": "test-import-001"},
        files=files,
        data={"file_roles": ["cadastro", "financeiro"]},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["persisted"] is True
    assert body["students_imported"] == 1
    assert body["quality"]["rows_created"] == 1
    students = await client.get("/api/v1/students", headers={"X-API-Key": key})
    row = next(s for s in students.json()["students"] if s["matricula"] == "00123")
    assert row["nome"] == "Ana Souza"
    assert row["curso"] == "Direito"
    assert row["dias_atraso_boleto"] == 12

    replay_files = [
        ("files", ("cadastro.csv", b"matricula,nome,curso\n00123,Ana Souza,Direito\n", "text/csv")),
        ("files", ("financeiro.csv", b"matricula,dias_atraso_boleto,recorrencia_atrasos\n00123,12,3\n", "text/csv")),
    ]
    replay = await client.post(
        "/api/v1/upload/confirm-multiple",
        headers={"X-API-Key": key, "Idempotency-Key": "test-import-001"},
        files=replay_files,
        data={"file_roles": ["cadastro", "financeiro"]},
    )
    assert replay.status_code == 201, replay.text
    assert replay.json()["idempotent_replay"] is True
    assert replay.json()["batch"]["id"] == body["batch"]["id"]


@pytest.mark.asyncio
async def test_confirm_multiple_blocks_conflicts_without_persisting(client, tenant):
    _tenant, key = tenant
    files = [
        ("files", ("cadastro-a.csv", b"matricula,nome,curso\n00123,Ana Souza,Direito\n", "text/csv")),
        ("files", ("cadastro-b.csv", b"matricula,nome,curso\n00123,Ana Souza,Medicina\n", "text/csv")),
    ]
    response = await client.post(
        "/api/v1/upload/confirm-multiple",
        headers={"X-API-Key": key, "Idempotency-Key": "test-import-conflict"},
        files=files,
        data={"file_roles": ["cadastro", "cadastro"]},
    )
    assert response.status_code == 422, response.text
    students = await client.get("/api/v1/students", headers={"X-API-Key": key})
    assert students.json()["count"] == 0


@pytest.mark.asyncio
async def test_refreshing_predictive_source_invalidates_current_score_but_preserves_history(
    client, tenant, db_session
):
    tenant_obj, key = tenant
    first_csv = (
        b"matricula,nome,dias_atraso_boleto,recorrencia_atrasos,dias_sem_login,"
        b"presenca_percentual,nota_media,reprovacoes,semestre\n"
        b"QUALITY-001,Ana,0,0,0,95,8,0,3\n"
    )
    first = await client.post(
        "/api/v1/upload",
        headers={"X-API-Key": key},
        files=_upload(first_csv, "complete.csv"),
        params={"auto_score": "false"},
    )
    assert first.status_code == 201, first.text
    student = (
        await db_session.execute(
            select(Student).where(Student.tenant_id == tenant_obj.id, Student.matricula == "QUALITY-001")
        )
    ).scalar_one()
    student.risk_score = 18.0
    student.risk_level = "baixo"
    student.model_risk_score = 16.0
    student.shap_top_factors = {"feature_schema_version": "legacy"}
    await db_session.commit()

    # A blank refresh is not allowed to keep using the previous 8.0 as current evidence.
    refresh_csv = (
        b"matricula,nome,nota_media\n"
        b"QUALITY-001,Ana,\n"
    )
    refresh = await client.post(
        "/api/v1/upload",
        headers={"X-API-Key": key},
        files=_upload(refresh_csv, "grade-refresh.csv"),
        params={"auto_score": "false"},
    )
    assert refresh.status_code == 201, refresh.text
    await db_session.refresh(student)
    assert student.risk_score is None
    assert student.risk_level is None
    assert student.model_risk_score is None
    assert student.shap_top_factors is None
    # Existing assessment rows are not deleted by ingestion.


@pytest.mark.asyncio
async def test_blank_predictive_alias_invalidates_score_and_updates_canonical_raw_data(
    client, tenant, db_session
):
    tenant_obj, key = tenant
    first_csv = (
        b"matricula,nome,dias_atraso_boleto,recorrencia_atrasos,dias_sem_login,"
        b"presenca_percentual,nota_media,reprovacoes,semestre\n"
        b"QUALITY-ALIAS-001,Ana,0,0,0,95,8,0,3\n"
    )
    first = await client.post(
        "/api/v1/upload",
        headers={"X-API-Key": key},
        files=_upload(first_csv, "complete.csv"),
        params={"auto_score": "false"},
    )
    assert first.status_code == 201, first.text
    student = (
        await db_session.execute(
            select(Student).where(
                Student.tenant_id == tenant_obj.id,
                Student.matricula == "QUALITY-ALIAS-001",
            )
        )
    ).scalar_one()
    student.risk_score = 22.0
    student.risk_level = "baixo"
    student.shap_top_factors = {"feature_schema_version": "legacy"}
    await db_session.commit()

    # Alias is normalized to the canonical predictive field before persistence.
    refresh_csv = b"matricula,nome,Average Grade\nQUALITY-ALIAS-001,Ana,\n"
    refresh = await client.post(
        "/api/v1/upload",
        headers={"X-API-Key": key},
        files=_upload(refresh_csv, "grade-alias-refresh.csv"),
        params={"auto_score": "false"},
    )
    assert refresh.status_code == 201, refresh.text
    await db_session.refresh(student)
    assert student.risk_score is None
    assert student.risk_level is None
    assert student.raw_data["nota_media"] is None
