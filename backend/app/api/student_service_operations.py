"""Institutional Academic Service Desk — Wave 5.

No unapproved external sends, payments, automated document signatures or
third-party downloads. Every object is resolved under the authenticated tenant;
students are resolved exclusively from their revocable portal session.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import and_, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.native_academic import PortalIdentity, _portal_action, _portal_identity, _require_ies, _student
from app.api.student_services import _enabled, _human, _request_json
from app.core.auth import AuthContext, require_permission
from app.db.session import get_db
from app.models.auth import User
from app.models.organization import Membership
from app.models.student_services import (
    StudentDocument, StudentDocumentTemplate, StudentServiceAttachment,
    StudentServiceComment, StudentServiceEvent, StudentServiceNotification,
    StudentServiceRequest,
)

institution_router = APIRouter(prefix="/native-academic/services", tags=["Central de Serviços Acadêmicos"])
portal_router = APIRouter(prefix="/student-portal/services", tags=["Portal do Aluno — acompanhamento"])
PRIORITIES = ("low", "normal", "high", "urgent")
DOCUMENT_KINDS = ("declaration", "enrollment_proof", "transcript", "other")
CATEGORIES = ("declaration", "transcript", "enrollment", "academic_review", "other")
MAX_ATTACHMENT_BYTES = 262144
MAX_ATTACHMENTS = 5
ALLOWED_VARIABLES = frozenset({
    "student_name", "registration", "organization_name", "today",
    "request_subject", "request_description",
})
VARIABLE_RE = re.compile(r"{{\s*([a-z_]+)\s*}}")
ANY_VARIABLE_RE = re.compile(r"{{.*?}}", flags=re.DOTALL)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _deny_missing():
    raise HTTPException(status_code=404, detail="Solicitação não encontrada.")


def _stamp(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _queue_json(row: StudentServiceRequest) -> dict:
    return {
        **_request_json(row),
        "student_id": row.student_id,
        "assigned_membership_id": row.assigned_membership_id,
        "due_at": _stamp(row.due_at),
        "assigned_at": _stamp(row.assigned_at),
        "completed_at": _stamp(row.completed_at),
        "priority": row.priority,
        "generated_document_id": row.generated_document_id,
    }


async def _get_request(
    db: AsyncSession, tenant_id: str, request_id: UUID, *,
    student_id: str | None = None, lock: bool = False,
) -> StudentServiceRequest:
    q = select(StudentServiceRequest).where(
        StudentServiceRequest.tenant_id == tenant_id,
        StudentServiceRequest.id == str(request_id),
    )
    if student_id is not None:
        q = q.where(StudentServiceRequest.student_id == student_id)
    if lock:
        q = q.with_for_update()
    row = (await db.execute(q)).scalar_one_or_none()
    if row is None:
        _deny_missing()
    return row


async def _institution(auth: AuthContext, db: AsyncSession) -> None:
    _enabled()
    _human(auth)
    await _require_ies(db, auth)


def _audit(db: AsyncSession, row: StudentServiceRequest, actor_type: str,
           actor_user_id: str | None, note: str) -> None:
    db.add(StudentServiceEvent(
        tenant_id=row.tenant_id, request_id=row.id,
        actor_type=actor_type, actor_user_id=actor_user_id,
        status=row.status, note=note[:500],
    ))


def _notify_student(db: AsyncSession, row: StudentServiceRequest, key: str, title: str):
    db.add(StudentServiceNotification(
        tenant_id=row.tenant_id, request_id=row.id, recipient_kind="student",
        student_id=row.student_id, event_key=key, title=title[:180],
    ))


async def _notify_assignee(
    db: AsyncSession, row: StudentServiceRequest, key: str, title: str,
) -> None:
    if not row.assigned_membership_id:
        return
    member = (await db.execute(select(Membership).where(
        Membership.id == row.assigned_membership_id,
        Membership.tenant_id == row.tenant_id,
        Membership.status == "active",
    ))).scalar_one_or_none()
    if member:
        db.add(StudentServiceNotification(
            tenant_id=row.tenant_id, request_id=row.id, recipient_kind="staff",
            staff_user_id=member.user_id, event_key=key, title=title[:180],
        ))


class AssignPayload(BaseModel):
    membership_id: UUID
    priority: Literal["low", "normal", "high", "urgent"] = "normal"
    due_at: datetime | None = None

    @field_validator("due_at")
    @classmethod
    def validate_due(cls, value: datetime | None):
        if value is not None and (value.tzinfo is None
                                  or value <= _now()
                                  or value > _now() + timedelta(days=366)):
            raise ValueError("Prazo deve ser futuro e ter fuso horário (máximo 366 dias).")
        return value


class CommentPayload(BaseModel):
    body: str = Field(min_length=1, max_length=2000)
    visibility: Literal["student", "staff"] = "student"

    @field_validator("body")
    @classmethod
    def trim_body(cls, value: str):
        if not value.strip():
            raise ValueError("Comentário vazio.")
        return value.strip()


class TemplatePayload(BaseModel):
    name: str = Field(min_length=3, max_length=120)
    category: Literal["declaration", "transcript", "enrollment", "academic_review", "other"]
    document_kind: Literal["declaration", "enrollment_proof", "transcript", "other"]
    body_template: str = Field(min_length=10, max_length=10000)
    is_active: bool = True

    @field_validator("body_template")
    @classmethod
    def valid_template(cls, value: str):
        valid = set(VARIABLE_RE.findall(value))
        if valid - ALLOWED_VARIABLES:
            raise ValueError("Variável de documento desconhecida.")
        if len(ANY_VARIABLE_RE.findall(value)) != len(VARIABLE_RE.findall(value)):
            raise ValueError("Marcador de modelo inválido.")
        if "{{" in VARIABLE_RE.sub("", value) or "}}" in VARIABLE_RE.sub("", value):
            raise ValueError("Marcador de modelo inválido.")
        return value


class GeneratePayload(BaseModel):
    template_id: UUID


def render_template(body: str, values: dict[str, str]) -> str:
    # Fixed allowlist: never eval(), execute HTML, or treat student content as instructions.
    if len(ANY_VARIABLE_RE.findall(body)) != len(VARIABLE_RE.findall(body)):
        raise ValueError("Marcador inválido.")
    return VARIABLE_RE.sub(lambda m: values[m.group(1)], body)


async def _detail(db: AsyncSession, row: StudentServiceRequest, *, staff: bool) -> dict:
    condition = (
        StudentServiceComment.tenant_id == row.tenant_id,
        StudentServiceComment.request_id == row.id,
    )
    q = select(StudentServiceComment).where(*condition)
    if not staff:
        q = q.where(StudentServiceComment.visibility == "student")
    comments = (await db.execute(
        q.order_by(StudentServiceComment.created_at, StudentServiceComment.id).limit(300)
    )).scalars().all()

    q2 = select(StudentServiceAttachment).where(
        StudentServiceAttachment.tenant_id == row.tenant_id,
        StudentServiceAttachment.request_id == row.id,
    )
    if not staff:
        q2 = q2.where(StudentServiceAttachment.visibility == "student")
    files = (await db.execute(
        q2.order_by(StudentServiceAttachment.created_at, StudentServiceAttachment.id).limit(20)
    )).scalars().all()
    return {
        "request": _queue_json(row) if staff else _request_json(row),
        "comments": [{
            "id": c.id, "actor_type": c.actor_type, "body": c.body,
            "visibility": c.visibility, "created_at": _stamp(c.created_at),
        } for c in comments],
        "attachments": [{
            "id": f.id, "filename": f.filename, "content_type": f.content_type,
            "byte_count": f.byte_count, "visibility": f.visibility,
            "created_at": _stamp(f.created_at),
        } for f in files],
    }


@institution_router.get("/queue")
async def service_queue(
    status: Literal["submitted", "in_review", "approved", "rejected", "completed", "cancelled"] | None = None,
    priority: Literal["low", "normal", "high", "urgent"] | None = None,
    membership_id: UUID | None = None,
    limit: int = 50, offset: int = 0,
    auth: AuthContext = Depends(require_permission("students.sensitive.view")),
    db: AsyncSession = Depends(get_db),
):
    await _institution(auth, db)
    if limit < 1 or limit > 100 or offset < 0 or offset > 10000:
        raise HTTPException(status_code=422, detail="Paginação inválida.")
    filters = [StudentServiceRequest.tenant_id == auth.tenant_id]
    if status:
        filters.append(StudentServiceRequest.status == status)
    if priority:
        filters.append(StudentServiceRequest.priority == priority)
    if membership_id:
        filters.append(StudentServiceRequest.assigned_membership_id == str(membership_id))
    total = (await db.execute(select(func.count()).select_from(StudentServiceRequest).where(*filters))).scalar_one()
    rows = (await db.execute(
        select(StudentServiceRequest).where(*filters)
        .order_by(StudentServiceRequest.due_at.asc().nullslast(), StudentServiceRequest.created_at.desc())
        .offset(offset).limit(limit)
    )).scalars().all()
    return {"items": [_queue_json(row) for row in rows], "total": total,
            "limit": limit, "offset": offset, "has_more": offset + len(rows) < total}


@institution_router.get("/staff")
async def service_staff(
    auth: AuthContext = Depends(require_permission("students.sensitive.view")),
    db: AsyncSession = Depends(get_db),
):
    await _institution(auth, db)
    rows = (await db.execute(
        select(Membership.id, User.display_name)
        .join(User, User.id == Membership.user_id)
        .where(Membership.tenant_id == auth.tenant_id, Membership.status == "active", User.is_active.is_(True))
        .order_by(User.display_name).limit(300)
    )).all()
    return {"items": [{"membership_id": mid, "display_name": name} for mid, name in rows]}


@institution_router.get("/requests/{request_id}/detail")
async def institution_detail(
    request_id: UUID,
    auth: AuthContext = Depends(require_permission("students.sensitive.view")),
    db: AsyncSession = Depends(get_db),
):
    await _institution(auth, db)
    row = await _get_request(db, auth.tenant_id, request_id)
    detail = await _detail(db, row, staff=True)
    student = await _student(db, auth.tenant_id, row.student_id)
    detail["student"] = {"id": student.id, "name": student.nome,
                         "registration": student.matricula, "course": student.curso}
    return detail


@portal_router.get("/requests/{request_id}/detail")
async def portal_detail(
    request_id: UUID,
    identity: PortalIdentity = Depends(_portal_identity),
    db: AsyncSession = Depends(get_db),
):
    _enabled()
    row = await _get_request(db, identity.tenant_id, request_id, student_id=identity.student.id)
    return await _detail(db, row, staff=False)


@institution_router.post("/requests/{request_id}/assign")
async def assign_request(
    request_id: UUID, body: AssignPayload,
    auth: AuthContext = Depends(require_permission("students.edit")),
    db: AsyncSession = Depends(get_db),
):
    await _institution(auth, db)
    row = await _get_request(db, auth.tenant_id, request_id, lock=True)
    if row.status in ("completed", "rejected", "cancelled"):
        raise HTTPException(status_code=409, detail="Solicitação encerrada.")
    member = (await db.execute(
        select(Membership, User.is_active)
        .join(User, User.id == Membership.user_id)
        .where(Membership.tenant_id == auth.tenant_id,
               Membership.id == str(body.membership_id),
               Membership.status == "active")
    )).one_or_none()
    if not member or not member[1]:
        raise HTTPException(status_code=404, detail="Responsável não disponível neste workspace.")
    row.assigned_membership_id = member[0].id
    row.assigned_at = _now()
    row.priority = body.priority
    row.due_at = body.due_at
    if row.status == "submitted":
        row.status = "in_review"
    row.updated_at = _now()
    _audit(db, row, "staff", auth.user_id, "Responsável e prazo definidos.")
    await _notify_assignee(db, row, "assigned", "Nova solicitação atribuída a você")
    _notify_student(db, row, "in_review", "Sua solicitação está em análise")
    await db.commit()
    return _queue_json(row)


@institution_router.post("/requests/{request_id}/comments", status_code=201)
async def staff_comment(
    request_id: UUID, body: CommentPayload,
    auth: AuthContext = Depends(require_permission("students.edit")),
    db: AsyncSession = Depends(get_db),
):
    await _institution(auth, db)
    row = await _get_request(db, auth.tenant_id, request_id, lock=True)
    if row.status in ("completed", "rejected", "cancelled"):
        raise HTTPException(status_code=409, detail="Solicitação encerrada.")
    item = StudentServiceComment(
        tenant_id=auth.tenant_id, request_id=row.id, actor_type="staff",
        actor_user_id=auth.user_id, visibility=body.visibility, body=body.body,
    )
    db.add(item)
    _audit(db, row, "staff", auth.user_id, "Comentário institucional registrado.")
    if body.visibility == "student":
        _notify_student(db, row, "comment", "A equipe respondeu à sua solicitação")
    await db.commit()
    return {"id": item.id, "visibility": item.visibility, "created_at": _stamp(item.created_at)}


@portal_router.post("/requests/{request_id}/comments", status_code=201)
async def portal_comment(
    request_id: UUID, body: CommentPayload, request: Request,
    identity: PortalIdentity = Depends(_portal_identity),
    db: AsyncSession = Depends(get_db),
):
    _enabled()
    _portal_action(request)
    if body.visibility != "student":
        raise HTTPException(status_code=403, detail="Comentário interno não permitido.")
    row = await _get_request(db, identity.tenant_id, request_id, student_id=identity.student.id, lock=True)
    if row.status in ("completed", "rejected", "cancelled"):
        raise HTTPException(status_code=409, detail="Solicitação encerrada.")
    item = StudentServiceComment(
        tenant_id=identity.tenant_id, request_id=row.id, actor_type="student",
        visibility="student", body=body.body,
    )
    db.add(item)
    _audit(db, row, "student", None, "Nova resposta do aluno.")
    await _notify_assignee(db, row, "student_reply", "Aluno respondeu à solicitação")
    await db.commit()
    return {"id": item.id, "visibility": "student", "created_at": _stamp(item.created_at)}


def _validate_upload(filename: str, content_type: str, data: bytes) -> tuple[str, str]:
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", filename.replace("\\", "/").split("/")[-1])[:160]
    if not safe_name or safe_name in (".", ".."):
        raise HTTPException(status_code=422, detail="Nome do arquivo inválido.")
    if not data or len(data) > MAX_ATTACHMENT_BYTES:
        raise HTTPException(status_code=413, detail="Arquivo deve ter no máximo 256 KiB.")
    formats = {
        "application/pdf": (".pdf", data.startswith(b"%PDF-")),
        "image/png": (".png", data.startswith(b"\x89PNG\r\n\x1a\n")),
        "image/jpeg": ((".jpg", ".jpeg"), data.startswith(b"\xff\xd8\xff")),
    }
    allowed = formats.get(content_type)
    if not allowed or not safe_name.lower().endswith(allowed[0]) or not allowed[1]:
        raise HTTPException(status_code=415, detail="Somente PDF, PNG e JPG válidos são aceitos.")
    return safe_name, content_type


async def _add_attachment(db: AsyncSession, row: StudentServiceRequest,
                          file: UploadFile, actor: str, user_id: str | None, visibility: str):
    if row.status in ("completed", "rejected", "cancelled"):
        raise HTTPException(status_code=409, detail="Solicitação encerrada.")
    count = (await db.execute(select(func.count()).select_from(StudentServiceAttachment).where(
        StudentServiceAttachment.tenant_id == row.tenant_id,
        StudentServiceAttachment.request_id == row.id,
    ))).scalar_one()
    if count >= MAX_ATTACHMENTS:
        raise HTTPException(status_code=409, detail="Limite de cinco anexos por solicitação.")
    data = await file.read(MAX_ATTACHMENT_BYTES + 1)
    name, kind = _validate_upload(file.filename or "", file.content_type or "", data)
    item = StudentServiceAttachment(
        tenant_id=row.tenant_id, request_id=row.id, actor_type=actor,
        actor_user_id=user_id, visibility=visibility, filename=name,
        content_type=kind, byte_count=len(data),
        content_sha256=hashlib.sha256(data).hexdigest(), content=data,
    )
    db.add(item)
    _audit(db, row, actor, user_id, "Anexo adicionado à solicitação.")
    if actor == "staff" and visibility == "student":
        _notify_student(db, row, "attachment", "Novo anexo disponível na solicitação")
    elif actor == "student":
        await _notify_assignee(db, row, "attachment", "Aluno enviou um anexo")
    await db.commit()
    return {"id": item.id, "filename": item.filename, "byte_count": item.byte_count,
            "visibility": item.visibility}


@institution_router.post("/requests/{request_id}/attachments", status_code=201)
async def staff_upload(
    request_id: UUID, file: UploadFile = File(...),
    visibility: Literal["student", "staff"] = Form("staff"),
    auth: AuthContext = Depends(require_permission("students.edit")),
    db: AsyncSession = Depends(get_db),
):
    await _institution(auth, db)
    row = await _get_request(db, auth.tenant_id, request_id, lock=True)
    return await _add_attachment(db, row, file, "staff", auth.user_id, visibility)


@portal_router.post("/requests/{request_id}/attachments", status_code=201)
async def portal_upload(
    request_id: UUID, request: Request, file: UploadFile = File(...),
    identity: PortalIdentity = Depends(_portal_identity),
    db: AsyncSession = Depends(get_db),
):
    _enabled()
    _portal_action(request)
    row = await _get_request(db, identity.tenant_id, request_id, student_id=identity.student.id, lock=True)
    return await _add_attachment(db, row, file, "student", None, "student")


async def _download(db: AsyncSession, row: StudentServiceRequest, attachment_id: UUID, *,
                    staff: bool) -> Response:
    query = select(StudentServiceAttachment).where(
        StudentServiceAttachment.tenant_id == row.tenant_id,
        StudentServiceAttachment.request_id == row.id,
        StudentServiceAttachment.id == str(attachment_id),
    )
    if not staff:
        query = query.where(StudentServiceAttachment.visibility == "student")
    file = (await db.execute(query)).scalar_one_or_none()
    if not file:
        raise HTTPException(status_code=404, detail="Anexo não encontrado.")
    return Response(
        content=file.content, media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{file.filename}"',
                 "X-Content-Type-Options": "nosniff", "Cache-Control": "no-store",
                 "Content-Security-Policy": "sandbox"},
    )


@institution_router.get("/requests/{request_id}/attachments/{attachment_id}")
async def staff_download(
    request_id: UUID, attachment_id: UUID,
    auth: AuthContext = Depends(require_permission("students.sensitive.view")),
    db: AsyncSession = Depends(get_db),
):
    await _institution(auth, db)
    row = await _get_request(db, auth.tenant_id, request_id)
    return await _download(db, row, attachment_id, staff=True)


@portal_router.get("/requests/{request_id}/attachments/{attachment_id}")
async def portal_download(
    request_id: UUID, attachment_id: UUID,
    identity: PortalIdentity = Depends(_portal_identity),
    db: AsyncSession = Depends(get_db),
):
    _enabled()
    row = await _get_request(db, identity.tenant_id, request_id, student_id=identity.student.id)
    return await _download(db, row, attachment_id, staff=False)


async def _notifications(db: AsyncSession, tenant_id: str, kind: str, id_field, recipient_id: str):
    items = (await db.execute(
        select(StudentServiceNotification).where(
            StudentServiceNotification.tenant_id == tenant_id,
            StudentServiceNotification.recipient_kind == kind,
            id_field == recipient_id,
        ).order_by(StudentServiceNotification.created_at.desc()).limit(100)
    )).scalars().all()
    return {"items": [{
        "id": n.id, "request_id": n.request_id, "title": n.title,
        "event_key": n.event_key, "read_at": _stamp(n.read_at),
        "created_at": _stamp(n.created_at),
    } for n in items]}


@institution_router.get("/notifications")
async def staff_notifications(
    auth: AuthContext = Depends(require_permission("students.sensitive.view")),
    db: AsyncSession = Depends(get_db),
):
    await _institution(auth, db)
    return await _notifications(db, auth.tenant_id, "staff", StudentServiceNotification.staff_user_id, auth.user_id)


@portal_router.get("/notifications")
async def portal_notifications(
    identity: PortalIdentity = Depends(_portal_identity),
    db: AsyncSession = Depends(get_db),
):
    _enabled()
    return await _notifications(db, identity.tenant_id, "student", StudentServiceNotification.student_id, identity.student.id)


async def _mark_read(db: AsyncSession, tenant_id: str, kind: str, id_field, recipient_id: str, notification_id: UUID):
    n = (await db.execute(select(StudentServiceNotification).where(
        StudentServiceNotification.id == str(notification_id),
        StudentServiceNotification.tenant_id == tenant_id,
        StudentServiceNotification.recipient_kind == kind,
        id_field == recipient_id,
    ).with_for_update())).scalar_one_or_none()
    if not n:
        raise HTTPException(status_code=404, detail="Notificação não encontrada.")
    n.read_at = n.read_at or _now()
    await db.commit()
    return {"id": n.id, "read_at": _stamp(n.read_at)}


@institution_router.post("/notifications/{notification_id}/read")
async def staff_mark_read(
    notification_id: UUID,
    auth: AuthContext = Depends(require_permission("students.sensitive.view")),
    db: AsyncSession = Depends(get_db),
):
    await _institution(auth, db)
    return await _mark_read(db, auth.tenant_id, "staff", StudentServiceNotification.staff_user_id, auth.user_id, notification_id)


@portal_router.post("/notifications/{notification_id}/read")
async def portal_mark_read(
    notification_id: UUID, request: Request,
    identity: PortalIdentity = Depends(_portal_identity),
    db: AsyncSession = Depends(get_db),
):
    _enabled()
    _portal_action(request)
    return await _mark_read(db, identity.tenant_id, "student", StudentServiceNotification.student_id, identity.student.id, notification_id)


@institution_router.get("/templates")
async def list_templates(
    auth: AuthContext = Depends(require_permission("students.sensitive.view")),
    db: AsyncSession = Depends(get_db),
):
    await _institution(auth, db)
    rows = (await db.execute(select(StudentDocumentTemplate).where(
        StudentDocumentTemplate.tenant_id == auth.tenant_id,
    ).order_by(StudentDocumentTemplate.name).limit(200))).scalars().all()
    return {"items": [{
        "id": t.id, "name": t.name, "category": t.category,
        "document_kind": t.document_kind, "body_template": t.body_template,
        "is_active": t.is_active,
    } for t in rows], "variables": sorted(ALLOWED_VARIABLES)}


@institution_router.post("/templates", status_code=201)
async def create_template(
    body: TemplatePayload,
    auth: AuthContext = Depends(require_permission("settings.manage")),
    db: AsyncSession = Depends(get_db),
):
    await _institution(auth, db)
    item = StudentDocumentTemplate(
        tenant_id=auth.tenant_id, name=body.name.strip(),
        category=body.category, document_kind=body.document_kind,
        body_template=body.body_template, is_active=body.is_active,
        created_by_user_id=auth.user_id,
    )
    db.add(item)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Já existe um modelo com este nome.") from exc
    return {"id": item.id, "name": item.name}


@institution_router.put("/templates/{template_id}")
async def edit_template(
    template_id: UUID, body: TemplatePayload,
    auth: AuthContext = Depends(require_permission("settings.manage")),
    db: AsyncSession = Depends(get_db),
):
    await _institution(auth, db)
    item = (await db.execute(select(StudentDocumentTemplate).where(
        StudentDocumentTemplate.tenant_id == auth.tenant_id,
        StudentDocumentTemplate.id == str(template_id),
    ).with_for_update())).scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Modelo não encontrado.")
    item.name = body.name.strip()
    item.category = body.category
    item.document_kind = body.document_kind
    item.body_template = body.body_template
    item.is_active = body.is_active
    item.updated_at = _now()
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Já existe um modelo com este nome.") from exc
    return {"id": item.id, "name": item.name, "is_active": item.is_active}


@institution_router.post("/requests/{request_id}/document-draft", status_code=201)
async def generate_draft(
    request_id: UUID, body: GeneratePayload,
    auth: AuthContext = Depends(require_permission("students.edit")),
    db: AsyncSession = Depends(get_db),
):
    await _institution(auth, db)
    row = await _get_request(db, auth.tenant_id, request_id, lock=True)
    if row.status != "approved":
        raise HTTPException(status_code=409, detail="A solicitação precisa estar aprovada.")
    if row.generated_document_id:
        raise HTTPException(status_code=409, detail="Já existe um documento gerado para esta solicitação.")
    template = (await db.execute(select(StudentDocumentTemplate).where(
        StudentDocumentTemplate.tenant_id == auth.tenant_id,
        StudentDocumentTemplate.id == str(body.template_id),
        StudentDocumentTemplate.is_active.is_(True),
    ))).scalar_one_or_none()
    if not template or template.category != row.category:
        raise HTTPException(status_code=404, detail="Modelo não encontrado para esta categoria.")
    student = await _student(db, auth.tenant_id, row.student_id)
    rendered = render_template(template.body_template, {
        "student_name": student.nome,
        "registration": student.matricula,
        "organization_name": auth.tenant.name,
        "today": _now().date().strftime("%d/%m/%Y"),
        "request_subject": row.subject,
        "request_description": row.description,
    })
    if not 10 <= len(rendered) <= 10000:
        raise HTTPException(status_code=422, detail="Documento renderizado fora do limite.")
    document = StudentDocument(
        tenant_id=auth.tenant_id, student_id=row.student_id,
        kind=template.document_kind, title=template.name,
        content_text=rendered, publication_status="draft",
    )
    db.add(document)
    await db.flush()
    row.generated_document_id = document.id
    row.updated_at = _now()
    _audit(db, row, "staff", auth.user_id, "Rascunho de documento gerado para revisão.")
    await db.commit()
    return {"document_id": document.id, "publication_status": "draft",
            "download_available": False, "official_pdf": False}
