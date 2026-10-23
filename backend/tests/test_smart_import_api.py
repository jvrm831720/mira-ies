"""Integration tests for the guided, deterministic smart-import workflow."""
import json

import pytest
from sqlalchemy import select

from app.models.student import Student, UploadBatch


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
    second_csv = b"matricula,nome,curso\nKEEP-001,Nome Atual,Direito\n"
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

    students = list(
        (
            await db_session.execute(
                select(Student).where(Student.tenant_id == tenant_obj.id, Student.matricula == "KEEP-001")
            )
        ).scalars().all()
    )
    assert len(students) == 1
    assert students[0].id == original_id
    assert students[0].nome == "Nome Atual"
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
        b",Sem Matricula,missing@example.edu.br,80\n"
    )
    response = await client.post(
        "/api/v1/upload/preview", headers={"X-API-Key": key}, files=_upload(csv)
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["rows_received"] == 3
    assert body["rows_to_import"] == 1
    assert body["invalid_rows_count"] == 1
    assert body["duplicates_in_file"] == 1
    assert any("e-mail inválido" in warning for warning in body["warnings"])
    assert any("limitado" in warning for warning in body["warnings"])
    assert body["sample_rows"][0]["nome"] == "Ana Atual"


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
