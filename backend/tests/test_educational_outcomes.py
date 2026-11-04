from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import select

from app.models.educational_outcome import AcademicOutcome
from app.models.intervention import InterventionLog
from app.models.student import Student, UploadBatch


def _batch(tenant, name):
    return UploadBatch(
        filename=f"{name}.csv",
        original_filename=f"{name}.csv",
        status="scored",
        tenant_id=tenant.id,
    )


async def _student(session, tenant, matricula, course="Enfermagem"):
    batch = _batch(tenant, matricula)
    session.add(batch)
    await session.flush()
    student = Student(
        batch_id=batch.id,
        tenant_id=tenant.id,
        matricula=matricula,
        nome=f"Aluno {matricula}",
        curso=course,
    )
    session.add(student)
    await session.flush()
    return student


async def test_academic_outcome_ingests_without_risk_snapshot_and_is_idempotent(
    client, auth_headers, tenant, db_session,
):
    tenant_obj, _key = tenant
    student = await _student(db_session, tenant_obj, "ACA-1")
    await db_session.commit()
    observed_at = datetime.now(timezone.utc) - timedelta(days=2)
    payload = {
        "outcomes": [{
            "student_id": student.id,
            "matricula": student.matricula,
            "outcome": "rematriculado",
            "observed_at": observed_at.isoformat(),
            "academic_period": "2026.2",
            "source": "JACAD",
            "source_record_id": "matricula-2026-2-ACA-1",
        }],
    }

    first = await client.post("/api/v1/academic-outcomes", headers=auth_headers, json=payload)
    assert first.status_code == 201, first.text
    assert first.json()["created"] == 1
    assert first.json()["linked_training_events"] == 0

    # A repeated delivery updates the same source record, without creating a duplicate.
    payload["outcomes"][0]["outcome"] = "ativo"
    second = await client.post("/api/v1/academic-outcomes", headers=auth_headers, json=payload)
    assert second.status_code == 201, second.text
    assert second.json()["updated"] == 1

    rows = (await db_session.execute(
        select(AcademicOutcome).where(AcademicOutcome.tenant_id == tenant_obj.id)
    )).scalars().all()
    assert len(rows) == 1
    assert rows[0].outcome == "ativo"
    assert rows[0].academic_period == "2026.2"
    assert rows[0].source == "jacad"


async def test_educational_analytics_separates_confirmed_outcomes_from_contact_operations(
    client, auth_headers, tenant, tenant_factory, db_session,
):
    tenant_obj, _key = tenant
    other_tenant, _other_key = await tenant_factory(slug="other-ies", name="Outra IES")
    student_retained = await _student(db_session, tenant_obj, "PERM-1")
    student_evasion = await _student(db_session, tenant_obj, "PERM-2")
    other_student = await _student(db_session, other_tenant, "OTHER-1")
    await db_session.flush()
    observed_at = datetime.now(timezone.utc) - timedelta(days=1)
    db_session.add_all([
        AcademicOutcome(
            tenant_id=tenant_obj.id,
            student_id=student_retained.id,
            matricula=student_retained.matricula,
            course="Enfermagem",
            academic_period="2026.1",
            outcome="rematriculado",
            observed_at=observed_at,
            source="jacad",
            source_record_id="perm-1-2026-1",
        ),
        AcademicOutcome(
            tenant_id=tenant_obj.id,
            student_id=student_evasion.id,
            matricula=student_evasion.matricula,
            course="Enfermagem",
            academic_period="2026.1",
            outcome="evadiu",
            observed_at=observed_at,
            source="sponte",
            source_record_id="perm-2-2026-1",
        ),
        AcademicOutcome(
            tenant_id=other_tenant.id,
            student_id=other_student.id,
            matricula=other_student.matricula,
            course="Enfermagem",
            academic_period="2026.1",
            outcome="rematriculado",
            observed_at=observed_at,
            source="jacad",
            source_record_id="other-2026-1",
        ),
        InterventionLog(
            tenant_id=tenant_obj.id,
            student_id=student_retained.id,
            matricula=student_retained.matricula,
            channel="whatsapp",
            status="sent",
            delivery_status="delivered",
            campaign_id=str(uuid4()),
            created_at=observed_at - timedelta(days=5),
        ),
        InterventionLog(
            tenant_id=other_tenant.id,
            student_id=other_student.id,
            matricula=other_student.matricula,
            channel="whatsapp",
            status="sent",
            delivery_status="delivered",
            created_at=observed_at - timedelta(days=5),
        ),
    ])
    await db_session.commit()

    response = await client.get(
        "/api/v1/outcomes/analytics",
        headers=auth_headers,
        params={"days": 90, "academic_period": "2026.1", "course": "Enfermagem"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    education = body["educational"]
    assert education["summary"]["confirmed_outcomes"] == 2
    assert education["summary"]["unique_students"] == 2
    assert education["summary"]["rematriculados"] == 1
    assert education["summary"]["evasion_outcomes"] == 1
    assert education["summary"]["permanence_rate_pct"] == 50.0
    assert education["summary"]["academic_period_coverage_pct"] == 100.0
    assert education["by_academic_period"][0]["key"] == "2026.1"
    assert len(education["records"]) == 2

    operations = body["operational"]
    assert operations["summary"]["messages_sent"] == 1
    assert operations["summary"]["unique_students_contacted"] == 1
    assert operations["summary"]["delivered_messages"] == 1
    assert body["comparison"]["status"] == "insufficient_data"
    assert body["comparison"]["difference_percentage_points"] is None
    assert body["comparison"]["causal_claim"] is False


async def test_academic_outcome_rejects_student_from_another_tenant(
    client, auth_headers, tenant, tenant_factory, db_session,
):
    _tenant_obj, _key = tenant
    other_tenant, _ = await tenant_factory(slug="foreign-ies", name="IES Externa")
    foreign_student = await _student(db_session, other_tenant, "FOREIGN-1")
    await db_session.commit()

    response = await client.post(
        "/api/v1/academic-outcomes",
        headers=auth_headers,
        json={"outcomes": [{
            "student_id": foreign_student.id,
            "matricula": foreign_student.matricula,
            "outcome": "evadiu",
            "observed_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
            "source": "jacad",
        }]},
    )
    assert response.status_code == 201, response.text
    assert response.json()["created"] == 0
    assert "não encontrado para este tenant" in response.json()["errors"][0]["error"]
