"""Student profile fields are tenant-scoped, sourced from persisted records.

The financial balance is a source snapshot, not a payment confirmation.
"""

from app.models.student import Student, UploadBatch


async def test_student_record_requires_auth(client):
    response = await client.get("/api/v1/students/00000000-0000-0000-0000-000000000001/risk")
    assert response.status_code == 401


async def test_student_record_exposes_persisted_academic_fields(
    client, auth_headers, tenant, db_session,
):
    organization, _ = tenant
    batch = UploadBatch(
        tenant_id=organization.id,
        filename="student-profile.csv",
        original_filename="student-profile.csv",
    )
    db_session.add(batch)
    await db_session.flush()
    student = Student(
        tenant_id=organization.id,
        batch_id=batch.id,
        matricula="ST-PROFILE-1",
        nome="Aluno Perfil",
        curso="Administração",
        campus="Centro",
        status_aluno="ATIVO",
        turma="T-2026",
        semestre=3,
        presenca_percentual=83.0,
        nota_media=7.5,
        reprovacoes=1,
        dias_atraso_boleto=20,
        saldo_devedor=420.0,
        status_financeiro="VENCIDO",
    )
    db_session.add(student)
    await db_session.commit()

    response = await client.get(
        f"/api/v1/students/{student.id}/risk", headers=auth_headers
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["matricula"] == "ST-PROFILE-1"
    assert data["campus"] == "Centro"
    assert data["status_aluno"] == "ATIVO"
    assert data["turma"] == "T-2026"
    assert data["presenca_percentual"] == 83.0
    assert data["nota_media"] == 7.5
    assert data["reprovacoes"] == 1
    assert data["saldo_devedor"] == 420.0
    assert data["status_financeiro"] == "VENCIDO"


async def test_student_record_does_not_cross_tenant(
    client, tenant_factory, auth_headers, tenant, db_session,
):
    other, _ = await tenant_factory(slug="another-campus", name="Outra instituição")
    batch = UploadBatch(
        tenant_id=other.id, filename="other.csv", original_filename="other.csv"
    )
    db_session.add(batch)
    await db_session.flush()
    student = Student(
        tenant_id=other.id,
        batch_id=batch.id,
        matricula="OTHER-1",
        nome="Aluno de outra instituição",
    )
    db_session.add(student)
    await db_session.commit()
    response = await client.get(
        f"/api/v1/students/{student.id}/risk", headers=auth_headers
    )
    assert response.status_code == 404
