"""Single-recipient interventions and reviewed templates, beside bulk/targeted campaigns."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthContext, require_permission
from app.db.session import get_db
from app.services import dispatch_interventions as intervention
from app.services.dispatch_ingress_security import verify as verify_source

router = APIRouter(prefix="/dispatch", tags=["Individual Interventions"])


def actor_id(auth: AuthContext) -> str:
    if not auth.user_id:
        raise HTTPException(status_code=403, detail="Ação exige usuário humano autenticado.")
    return auth.user_id


class TemplateCreate(BaseModel):
    code: str = Field(min_length=2, max_length=100)
    purpose: Literal["retention", "academic", "service", "collections"]
    channel: Literal["email", "sms", "whatsapp"]
    subject: str = Field(min_length=3, max_length=160)
    body: str = Field(min_length=3, max_length=2000)


class TemplateApproval(BaseModel):
    evidence_ref: str = Field(min_length=8, max_length=200)


class InterventionCreate(BaseModel):
    template_id: str = Field(min_length=1, max_length=80)
    subject_type: Literal["student", "external"]
    subject_ref: str = Field(min_length=1, max_length=160)
    evidence_ref: str = Field(min_length=8, max_length=200)
    scheduled_for: datetime | None = None


class AuthorizationFact(BaseModel):
    source: str = Field(min_length=3, max_length=80)
    subject_type: Literal["student", "external"]
    subject_ref: str = Field(min_length=1, max_length=160)
    purpose: Literal["retention", "academic", "service", "collections"]
    channel: Literal["email", "sms", "whatsapp"]
    evidence_ref: str = Field(min_length=8, max_length=200)
    status: Literal["granted", "revoked", "expired"]
    verified_at: datetime
    expires_at: datetime


def to_http(exc: LookupError | ValueError) -> HTTPException:
    return HTTPException(
        status_code=404 if isinstance(exc, LookupError) else 422,
        detail=str(exc),
    )


@router.get("/templates")
async def list_templates(
    auth: AuthContext = Depends(require_permission("campaigns.view")),
    db: AsyncSession = Depends(get_db),
):
    return {"items": await intervention.templates(db, auth.tenant_id)}


@router.post("/templates", status_code=201)
async def create_template(
    body: TemplateCreate,
    auth: AuthContext = Depends(require_permission("campaigns.create")),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await intervention.create_template(
            db, tenant_id=auth.tenant_id, actor=actor_id(auth),
            code=body.code, purpose=body.purpose, channel=body.channel,
            subject=body.subject, body=body.body,
        )
    except ValueError as exc:
        await db.rollback()
        raise to_http(exc) from exc


@router.post("/templates/{template_id}/approve")
async def approve_template(
    template_id: str, body: TemplateApproval,
    auth: AuthContext = Depends(require_permission("campaigns.approve")),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await intervention.approve_template(
            db, tenant_id=auth.tenant_id, actor=actor_id(auth),
            template_id=template_id, evidence_ref=body.evidence_ref,
        )
    except (ValueError, LookupError) as exc:
        await db.rollback()
        raise to_http(exc) from exc


@router.post("/interventions", status_code=201)
async def submit_individual_intervention(
    body: InterventionCreate,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    auth: AuthContext = Depends(require_permission("campaigns.execute")),
    db: AsyncSession = Depends(get_db),
):
    """A single authorized student/recipient, idempotently queued for the worker.

    A previously approved template and a current per-recipient authorization
    replace second approval for this low-risk operation. No SMS/email is sent
    synchronously from this HTTP request.
    """
    try:
        return await intervention.create_intervention(
            db, tenant_id=auth.tenant_id, actor=actor_id(auth),
            template_id=body.template_id, subject_type=body.subject_type,
            subject_ref=body.subject_ref, evidence_ref=body.evidence_ref,
            idempotency_key=idempotency_key, scheduled_for=body.scheduled_for,
        )
    except (ValueError, LookupError) as exc:
        await db.rollback()
        raise to_http(exc) from exc


@router.post("/integrations/authorizations")
async def upsert_authorization_fact(
    body: AuthorizationFact,
    request: Request,
    auth: AuthContext = Depends(require_permission("data.import", allow_service_key=True)),
    db: AsyncSession = Depends(get_db),
):
    # Verified tenant API keys are currently represented with role="admin".
    # A connector is not a human: reject user sessions, then require signed HMAC.
    if auth.user_id is not None or auth.session_id is not None:
        raise HTTPException(status_code=403, detail="Apenas conectores autenticados podem registrar fatos.")
    await verify_source(
        db,tenant_id=auth.tenant_id,source=body.source,
        scope="authorization",request=request,
    )
    try:
        return await intervention.sync_authorization(
            db, tenant_id=auth.tenant_id,
            source=body.source, subject_type=body.subject_type,
            subject_ref=body.subject_ref, channel=body.channel,
            purpose=body.purpose, evidence_ref=body.evidence_ref,
            status=body.status, verified_at=body.verified_at,
            expires_at=body.expires_at,
        )
    except ValueError as exc:
        await db.rollback()
        raise to_http(exc) from exc
