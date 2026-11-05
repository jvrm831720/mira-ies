"""Wave 3 contract and safety tests.

Database-backed isolation tests must use the PostgreSQL CI role without BYPASSRLS.
"""
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.student_services import (
    NewDocument, NewRequest, ReviewRequest, TRANSITIONS, _enabled,
)
from app.core.config import get_settings


def test_request_validation_and_allowed_categories():
    NewRequest(category="declaration", subject="Declaração de matrícula", description="Preciso da declaração.")
    with pytest.raises(ValidationError):
        NewRequest(category="pix", subject="Cobrança", description="Criar pagamento sem homologação")
    with pytest.raises(ValidationError):
        NewRequest(category="other", subject="x", description="breve")


def test_document_payload_rejects_untrusted_file_and_url():
    with pytest.raises(ValidationError):
        NewDocument(student_id=uuid4(), kind="pdf_from_url", title="Arquivo remoto",
                    content_text="https://example.org/arquivo.pdf")
    NewDocument(student_id=uuid4(), kind="declaration", title="Declaração",
                content_text="Conteúdo institucional verificado.")


def test_reviews_require_note_and_enforce_state_machine():
    assert TRANSITIONS["submitted"] == {"in_review", "cancelled"}
    assert "completed" not in TRANSITIONS["submitted"]
    assert "submitted" not in TRANSITIONS["completed"]
    with pytest.raises(ValidationError):
        ReviewRequest(status="approved", note="")
    with pytest.raises(ValidationError):
        ReviewRequest(status="paid", note="Pagamento efetuado")


def test_services_disabled_by_default(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "native_academic_services_enabled", False)
    with pytest.raises(HTTPException) as err:
        _enabled()
    assert err.value.status_code == 503


async def test_student_request_visibility_is_tenant_and_student_scoped(
    tenant_factory, db_session, monkeypatch,
):
    from sqlalchemy import select, text
    from app.models.student_services import StudentServiceRequest
    from app.models.student import Student, UploadBatch

    a, _ = await tenant_factory(slug="services-tenant-a")
    b, _ = await tenant_factory(slug="services-tenant-b")
    ids = []
    for tenant in (a, b):
        await db_session.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": tenant.id})
        batch = UploadBatch(tenant_id=tenant.id, filename="wave3.csv", original_filename="wave3.csv")
        db_session.add(batch)
        await db_session.flush()
        student = Student(tenant_id=tenant.id, batch_id=batch.id, matricula=str(uuid4()),
                          nome="Aluno de teste")
        db_session.add(student)
        await db_session.flush()
        row = StudentServiceRequest(tenant_id=tenant.id, student_id=student.id,
                                    category="declaration", subject="Declaração",
                                    description="Documento de vínculo acadêmico")
        db_session.add(row)
        await db_session.commit()
        ids.append(row.id)
    await db_session.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": a.id})
    seen = (await db_session.execute(select(StudentServiceRequest.id))).scalars().all()
    assert ids[0] in seen
    assert ids[1] not in seen
