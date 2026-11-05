"""Student self-service Wave 3.

The student identity is derived exclusively from the revocable portal session.
Institutional review requires a human session and an explicit permission.
No payment initiation, file upload, communication dispatch, or provider calls.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.native_academic import PortalIdentity, _portal_action, _portal_identity, _require_ies, _student
from app.core.auth import AuthContext, require_permission
from app.core.config import get_settings
from app.db.session import get_db
from app.models.student_services import (
    StudentDocument, StudentFinancialReference, StudentServiceEvent, StudentServiceRequest,
)

portal_router = APIRouter(prefix="/student-portal/services", tags=["Portal do Aluno — serviços"])
institution_router = APIRouter(prefix="/native-academic/services", tags=["Serviços acadêmicos institucionais"])

CATEGORIES = Literal["declaration", "transcript", "enrollment", "academic_review", "other"]
STATES = Literal["in_review", "approved", "rejected", "completed", "cancelled"]
TRANSITIONS = {
    "submitted": {"in_review", "cancelled"},
    "in_review": {"approved", "rejected", "cancelled"},
    "approved": {"completed", "cancelled"},
    "rejected": set(),
    "completed": set(),
    "cancelled": set(),
}


def _enabled():
    settings = get_settings()
    if not (settings.native_academic_enabled and settings.student_portal_enabled
            and settings.native_academic_services_enabled):
        raise HTTPException(status_code=503, detail="Serviços do aluno em homologação.")


def _human(auth: AuthContext):
    if not auth.user_id or not auth.session_id:
        raise HTTPException(status_code=403, detail="Exige sessão institucional humana.")


def _request_json(row):
    return {
        "id": row.id, "category": row.category, "subject": row.subject,
        "description": row.description, "status": row.status,
        "created_at": row.created_at.isoformat(), "updated_at": row.updated_at.isoformat(),
    }


class NewRequest(BaseModel):
    category: CATEGORIES
    subject: str = Field(min_length=3, max_length=180)
    description: str = Field(min_length=5, max_length=2000)


class ReviewRequest(BaseModel):
    status: STATES
    note: str = Field(min_length=3, max_length=500)


class NewDocument(BaseModel):
    student_id: UUID
    kind: Literal["declaration", "enrollment_proof", "transcript", "other"]
    title: str = Field(min_length=3, max_length=180)
    content_text: str = Field(min_length=10, max_length=10000)


@portal_router.post("/requests", status_code=201)
async def submit_request(
    body: NewRequest, request: Request,
    identity: PortalIdentity = Depends(_portal_identity),
    db: AsyncSession = Depends(get_db),
):
    _enabled()
    _portal_action(request)
    row = StudentServiceRequest(
        tenant_id=identity.tenant_id, student_id=identity.student.id,
        category=body.category, subject=body.subject, description=body.description,
    )
    db.add(row)
    await db.flush()
    db.add(StudentServiceEvent(
        tenant_id=identity.tenant_id, request_id=row.id, actor_type="student", status="submitted",
    ))
    await db.commit()
    return _request_json(row)


@portal_router.get("/requests")
async def my_requests(
    identity: PortalIdentity = Depends(_portal_identity),
    db: AsyncSession = Depends(get_db),
):
    _enabled()
    rows = (await db.execute(select(StudentServiceRequest).where(
        StudentServiceRequest.tenant_id == identity.tenant_id,
        StudentServiceRequest.student_id == identity.student.id,
    ).order_by(StudentServiceRequest.created_at.desc()).limit(100))).scalars().all()
    return {"items": [_request_json(row) for row in rows], "limit": 100}


@portal_router.get("/requests/{request_id}/history")
async def request_history(
    request_id: UUID,
    identity: PortalIdentity = Depends(_portal_identity),
    db: AsyncSession = Depends(get_db),
):
    _enabled()
    row = (await db.execute(select(StudentServiceRequest).where(
        StudentServiceRequest.id == str(request_id),
        StudentServiceRequest.tenant_id == identity.tenant_id,
        StudentServiceRequest.student_id == identity.student.id,
    ))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada.")
    events = (await db.execute(select(StudentServiceEvent).where(
        StudentServiceEvent.tenant_id == identity.tenant_id,
        StudentServiceEvent.request_id == row.id,
    ).order_by(StudentServiceEvent.occurred_at, StudentServiceEvent.id))).scalars().all()
    return {"request": _request_json(row), "events": [{
        "status": item.status, "note": item.note, "occurred_at": item.occurred_at.isoformat(),
    } for item in events]}


@institution_router.get("/requests")
async def institution_requests(
    auth: AuthContext = Depends(require_permission("students.sensitive.view")),
    db: AsyncSession = Depends(get_db),
):
    _enabled()
    _human(auth)
    await _require_ies(db, auth)
    rows = (await db.execute(select(StudentServiceRequest).where(
        StudentServiceRequest.tenant_id == auth.tenant_id,
    ).order_by(StudentServiceRequest.created_at.desc()).limit(200))).scalars().all()
    return {"items": [{**_request_json(row), "student_id": row.student_id} for row in rows]}


@institution_router.post("/requests/{request_id}/review")
async def review_request(
    request_id: UUID, body: ReviewRequest,
    auth: AuthContext = Depends(require_permission("critical.manage")),
    db: AsyncSession = Depends(get_db),
):
    _enabled()
    _human(auth)
    await _require_ies(db, auth)
    row = (await db.execute(select(StudentServiceRequest).where(
        StudentServiceRequest.tenant_id == auth.tenant_id,
        StudentServiceRequest.id == str(request_id),
    ).with_for_update())).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada.")
    if body.status not in TRANSITIONS[row.status]:
        raise HTTPException(status_code=409, detail="Transição de status inválida.")
    row.status = body.status
    row.updated_at = datetime.now(timezone.utc)
    db.add(StudentServiceEvent(
        tenant_id=auth.tenant_id, request_id=row.id, actor_type="staff",
        actor_user_id=auth.user_id, status=row.status, note=body.note,
    ))
    await db.commit()
    return _request_json(row)


@institution_router.post("/documents", status_code=201)
async def create_document(
    body: NewDocument,
    auth: AuthContext = Depends(require_permission("students.edit")),
    db: AsyncSession = Depends(get_db),
):
    _enabled()
    _human(auth)
    await _require_ies(db, auth)
    student = await _student(db, auth.tenant_id, str(body.student_id))
    row = StudentDocument(tenant_id=auth.tenant_id, student_id=student.id,
                          kind=body.kind, title=body.title, content_text=body.content_text)
    db.add(row)
    await db.commit()
    return {"id": row.id, "publication_status": "draft", "download_available": False}


@institution_router.post("/documents/{document_id}/publish")
async def publish_document(
    document_id: UUID,
    auth: AuthContext = Depends(require_permission("critical.manage")),
    db: AsyncSession = Depends(get_db),
):
    _enabled()
    _human(auth)
    await _require_ies(db, auth)
    row = (await db.execute(select(StudentDocument).where(
        StudentDocument.tenant_id == auth.tenant_id,
        StudentDocument.id == str(document_id),
    ).with_for_update())).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")
    if row.publication_status != "draft":
        raise HTTPException(status_code=409, detail="Documento não está em rascunho.")
    row.publication_status = "published"
    row.published_at = datetime.now(timezone.utc)
    await db.commit()
    return {"id": row.id, "publication_status": "published"}


@portal_router.get("/documents")
async def my_documents(
    identity: PortalIdentity = Depends(_portal_identity),
    db: AsyncSession = Depends(get_db),
):
    _enabled()
    rows = (await db.execute(select(StudentDocument).where(
        StudentDocument.tenant_id == identity.tenant_id,
        StudentDocument.student_id == identity.student.id,
        StudentDocument.publication_status == "published",
    ).order_by(StudentDocument.published_at.desc()).limit(100))).scalars().all()
    return {"items": [{"id": row.id, "title": row.title, "kind": row.kind,
                       "published_at": row.published_at.isoformat() if row.published_at else None}
                      for row in rows], "download_available": False}


@portal_router.get("/documents/{document_id}")
async def my_document(
    document_id: UUID,
    identity: PortalIdentity = Depends(_portal_identity),
    db: AsyncSession = Depends(get_db),
):
    _enabled()
    row = (await db.execute(select(StudentDocument).where(
        StudentDocument.tenant_id == identity.tenant_id,
        StudentDocument.student_id == identity.student.id,
        StudentDocument.id == str(document_id),
        StudentDocument.publication_status == "published",
    ))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")
    return {"id": row.id, "title": row.title, "kind": row.kind,
            "content_text": row.content_text, "format": "text_only", "official_pdf": False}


@portal_router.get("/financial")
async def financial_overview(
    identity: PortalIdentity = Depends(_portal_identity),
    db: AsyncSession = Depends(get_db),
):
    _enabled()
    rows = (await db.execute(select(StudentFinancialReference).where(
        StudentFinancialReference.tenant_id == identity.tenant_id,
        StudentFinancialReference.student_id == identity.student.id,
    ).order_by(StudentFinancialReference.observed_at.desc()).limit(100))).scalars().all()
    return {"items": [{
        "id": row.id, "label": row.label, "amount": str(row.amount),
        "currency": row.currency, "due_on": row.due_on.isoformat() if row.due_on else None,
        "status": row.source_status, "source": row.source, "observed_at": row.observed_at.isoformat(),
    } for row in rows], "snapshot_only": True, "payment_enabled": False,
        "note": "Valores informativos provenientes de integrações homologadas; não é uma cobrança."}
