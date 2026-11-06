"""Wave 5 — service desk safety, scope and complete student/staff lifecycle."""
import io
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import text, select
from starlette.datastructures import Headers, UploadFile

from app.api.student_service_operations import (
    AssignPayload, CommentPayload, GeneratePayload, TemplatePayload,
    _add_attachment, _download, _validate_upload, assign_request,
    generate_draft, institution_detail, portal_comment, portal_detail,
    portal_notifications, render_template, service_queue, staff_comment,
)
from app.api.student_services import ReviewRequest, publish_document, review_request
from app.core.config import get_settings
from app.models.auth import User
from app.models.organization import Membership
from app.models.student import Student, UploadBatch
from app.models.student_services import (
    StudentDocument, StudentDocumentTemplate, StudentServiceAttachment,
    StudentServiceNotification, StudentServiceRequest,
)


def test_wave5_schema_input_constraints_and_document_template_allowlist():
    assert AssignPayload(membership_id=uuid4(), priority="urgent").priority == "urgent"
    with pytest.raises(ValidationError):
        AssignPayload(membership_id=uuid4(), due_at=datetime.now() + timedelta(days=2))
    with pytest.raises(ValidationError):
        AssignPayload(membership_id=uuid4(), due_at=datetime.now(timezone.utc) - timedelta(days=2))
    with pytest.raises(ValidationError):
        AssignPayload(membership_id=uuid4(), priority="unlimited")
    with pytest.raises(ValidationError):
        CommentPayload(body=" ")
    with pytest.raises(ValidationError):
        TemplatePayload(name="Teste", category="declaration", document_kind="declaration",
                        body_template="Código {{__class__}} de sistema")
    with pytest.raises(ValidationError):
        TemplatePayload(name="Teste", category="declaration", document_kind="declaration",
                        body_template="Comando {{ student_name.__dict__ }}")
    body = "Declara-se: {{student_name}} / {{registration}}"
    TemplatePayload(name="Teste", category="declaration", document_kind="declaration",
                    body_template=body)
    assert render_template(body, {"student_name": "<Aluno>", "registration": "123"}) == "Declara-se: <Aluno> / 123"


def test_wave5_rejects_unsafe_attachments_and_enforces_signatures():
    assert _validate_upload("documento.pdf", "application/pdf", b"%PDF-1.7\nvalid")[0] == "documento.pdf"
    with pytest.raises(HTTPException) as mismatch:
        _validate_upload("x.pdf", "application/pdf", b"<script>alert(1)</script>")
    assert mismatch.value.status_code == 415
    with pytest.raises(HTTPException):
        _validate_upload("x.svg", "image/svg+xml", b"<svg/>")
    with pytest.raises(HTTPException):
        _validate_upload("x.pdf", "application/pdf", b"%PDF-" + (b"x" * 262144))
    with pytest.raises(HTTPException):
        _validate_upload("../../../evil.exe", "application/octet-stream", b"hello")


async def _tenant_case(db, tenant_factory, slug):
    tenant, _key = await tenant_factory(slug=slug)
    tenant.segment = "higher_education"
    await db.commit()
    await db.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": tenant.id})
    user = User(tenant_id=tenant.id, display_name="Equipe " + slug,
                email=slug+"@example.com", password_hash="unused", role="admin")
    db.add(user)
    await db.flush()
    member = Membership(tenant_id=tenant.id, user_id=user.id, role="admin",
                        status="active", origin="wave5_test")
    batch = UploadBatch(tenant_id=tenant.id, filename="wave5.csv", original_filename="wave5.csv")
    db.add_all([member, batch])
    await db.flush()
    student = Student(tenant_id=tenant.id, batch_id=batch.id,
                      matricula="MAT-" + slug, nome="Aluno " + slug)
    db.add(student)
    await db.flush()
    row = StudentServiceRequest(
        tenant_id=tenant.id, student_id=student.id, category="declaration",
        subject="Declaração de vínculo", description="Solicito declaração para comprovar matrícula.",
    )
    db.add(row)
    await db.commit()
    auth = SimpleNamespace(tenant=tenant, tenant_id=tenant.id, user_id=user.id,
                           role="admin", session_id=str(uuid4()), aal=2)
    identity = SimpleNamespace(tenant_id=tenant.id, student=student)
    return tenant, user, member, student, row, auth, identity


@pytest.mark.asyncio
async def test_wave5_isolated_staff_queue_and_student_portal_comment_visibility(
    db_session, tenant_factory, monkeypatch,
):
    for key in ("native_academic_enabled", "student_portal_enabled", "native_academic_services_enabled"):
        monkeypatch.setattr(get_settings(), key, True)
    a = await _tenant_case(db_session, tenant_factory, "wave5-school-a")
    b = await _tenant_case(db_session, tenant_factory, "wave5-school-b")
    await db_session.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": a[0].id})
    listing = await service_queue(auth=a[5], db=db_session)
    assert listing["total"] == 1
    assert listing["items"][0]["id"] == a[4].id
    with pytest.raises(HTTPException) as cross_tenant:
        await institution_detail(UUID(b[4].id), auth=a[5], db=db_session)
    assert cross_tenant.value.status_code == 404
    with pytest.raises(HTTPException) as cross_student:
        await portal_detail(UUID(b[4].id), identity=a[6], db=db_session)
    assert cross_student.value.status_code == 404

    assigned = await assign_request(UUID(a[4].id), AssignPayload(
        membership_id=UUID(a[2].id), priority="high",
        due_at=datetime.now(timezone.utc) + timedelta(days=4),
    ), auth=a[5], db=db_session)
    assert assigned["status"] == "in_review"
    assert assigned["priority"] == "high"
    assert assigned["assigned_membership_id"] == a[2].id
    await staff_comment(UUID(a[4].id), CommentPayload(
        body="Checar cadastro interno.", visibility="staff",
    ), auth=a[5], db=db_session)
    await staff_comment(UUID(a[4].id), CommentPayload(
        body="Estamos analisando seu pedido.", visibility="student",
    ), auth=a[5], db=db_session)
    detail_student = await portal_detail(UUID(a[4].id), identity=a[6], db=db_session)
    detail_staff = await institution_detail(UUID(a[4].id), auth=a[5], db=db_session)
    assert len(detail_student["comments"]) == 1
    assert len(detail_staff["comments"]) == 2
    assert "Checar cadastro" not in str(detail_student)
    notifications = await portal_notifications(identity=a[6], db=db_session)
    assert any(n["event_key"] == "comment" for n in notifications["items"])
    await portal_comment(UUID(a[4].id), CommentPayload(body="Obrigado!"), request=SimpleNamespace(
        headers={"x-mira-portal-action": "1"},
    ), identity=a[6], db=db_session)
    assert len((await institution_detail(UUID(a[4].id), auth=a[5], db=db_session))["comments"]) == 3


@pytest.mark.asyncio
async def test_wave5_approval_document_publication_and_completion(db_session, tenant_factory, monkeypatch):
    for key in ("native_academic_enabled", "student_portal_enabled", "native_academic_services_enabled"):
        monkeypatch.setattr(get_settings(), key, True)
    t, user, member, student, row, auth, identity = await _tenant_case(db_session, tenant_factory, "wave5-school-workflow")
    await db_session.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": t.id})
    with pytest.raises(HTTPException) as premature:
        await review_request(UUID(row.id), ReviewRequest(status="completed", note="Pronto"),
                             auth=auth, db=db_session)
    assert premature.value.status_code == 409
    await assign_request(UUID(row.id), AssignPayload(membership_id=UUID(member.id)),
                         auth=auth, db=db_session)
    await review_request(UUID(row.id), ReviewRequest(status="approved", note="Conferido"),
                         auth=auth, db=db_session)
    with pytest.raises(HTTPException) as missing_document:
        await review_request(UUID(row.id), ReviewRequest(status="completed", note="Finalizado"),
                             auth=auth, db=db_session)
    assert missing_document.value.status_code == 409
    template = StudentDocumentTemplate(
        tenant_id=t.id, name="Modelo de declaração Wave 5", category="declaration",
        document_kind="declaration", body_template="Confirmamos: {{student_name}} de {{organization_name}}. Data: {{today}}.",
        created_by_user_id=user.id,
    )
    db_session.add(template)
    await db_session.commit()
    draft = await generate_draft(UUID(row.id), GeneratePayload(template_id=UUID(template.id)),
                                 auth=auth, db=db_session)
    assert draft["publication_status"] == "draft"
    with pytest.raises(HTTPException):
        await review_request(UUID(row.id), ReviewRequest(status="completed", note="Finalizado"),
                             auth=auth, db=db_session)
    await publish_document(UUID(draft["document_id"]), auth=auth, db=db_session)
    closed = await review_request(UUID(row.id), ReviewRequest(status="completed", note="Documento publicado e entregue."),
                                  auth=auth, db=db_session)
    assert closed["status"] == "completed"
    stored = (await db_session.execute(select(StudentDocument).where(StudentDocument.id == draft["document_id"]))).scalar_one()
    assert stored.publication_status == "published"
    assert student.nome in stored.content_text
    with pytest.raises(HTTPException) as duplicate:
        await generate_draft(UUID(row.id), GeneratePayload(template_id=UUID(template.id)), auth=auth, db=db_session)
    assert duplicate.value.status_code == 409
    notices = (await db_session.execute(select(StudentServiceNotification).where(
        StudentServiceNotification.tenant_id == t.id,
        StudentServiceNotification.student_id == student.id,
    ))).scalars().all()
    assert any(n.event_key == "document" for n in notices)


@pytest.mark.asyncio
async def test_wave5_attachment_private_visibility_and_tenant_bound_download(
    db_session, tenant_factory, monkeypatch,
):
    for key in ("native_academic_enabled", "student_portal_enabled", "native_academic_services_enabled"):
        monkeypatch.setattr(get_settings(), key, True)
    a = await _tenant_case(db_session, tenant_factory, "wave5-school-files-a")
    b = await _tenant_case(db_session, tenant_factory, "wave5-school-files-b")
    await db_session.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": a[0].id})
    content = b"%PDF-1.7\nexample"
    upload = UploadFile(file=io.BytesIO(content), filename="historico.pdf",
                        headers=Headers({"content-type": "application/pdf"}))
    private = await _add_attachment(db_session, a[4], upload, "staff", a[1].id, "staff")
    assert private["visibility"] == "staff"
    detail = await portal_detail(UUID(a[4].id), identity=a[6], db=db_session)
    assert detail["attachments"] == []
    with pytest.raises(HTTPException) as hidden:
        await _download(db_session, a[4], UUID(private["id"]), staff=False)
    assert hidden.value.status_code == 404
    allowed = await _download(db_session, a[4], UUID(private["id"]), staff=True)
    assert allowed.body == content
    assert allowed.headers["x-content-type-options"] == "nosniff"
    with pytest.raises(HTTPException) as other_tenant:
        await portal_detail(UUID(b[4].id), identity=a[6], db=db_session)
    assert other_tenant.value.status_code == 404
    stored = (await db_session.execute(select(StudentServiceAttachment).where(
        StudentServiceAttachment.tenant_id == a[0].id,
    ))).scalars().all()
    assert len(stored) == 1
