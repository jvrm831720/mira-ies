"""Institutional payment drafts and sandbox-authenticated event ingress.

No live payment initiation or external PSP webhook approval is implemented.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.native_academic import PortalIdentity, _portal_identity, _require_ies
from app.core.auth import AuthContext, require_permission
from app.db.session import get_db
from app.models.student_payments import PaymentProviderProfile, StudentPaymentIntent, StudentPaymentEvidence
from app.services import student_payments as payments

router = APIRouter(prefix="/native-academic/finance/payments", tags=["Student payment sandbox"])
portal_router = APIRouter(prefix="/student-portal/services/payments", tags=["Student sandbox drafts"])
sandbox_router = APIRouter(prefix="/payment-sandbox/events", tags=["Signed sandbox event evidence"])


class ProviderCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    finance_profile_id: UUID
    name: str = Field(min_length=3, max_length=100)
    connection_kind: str = Field(pattern=r"^(composio|custom_pending)$")
    provider_slug: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,79}$")
    methods: list[str] = Field(min_length=1, max_length=2)


class ProviderEnable(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool
    expected_revision: int = Field(ge=1)


class PaymentDraftCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider_id: UUID
    financial_observation_id: UUID
    method: str = Field(pattern=r"^(pix|boleto)$")


def _summary_provider(row: PaymentProviderProfile):
    return {
        "id": row.id, "name": row.name, "finance_profile_id": row.finance_profile_id,
        "connection_kind": row.connection_kind, "provider_slug": row.provider_slug,
        "connected_account_id": row.connected_account_id,
        "methods": row.methods, "environment": "sandbox",
        "enabled": row.enabled, "revision": row.revision,
        "live_payments_enabled": False,
    }


def _require_staff(auth: AuthContext):
    if not auth.user_id or not auth.session_id or auth.aal < 2:
        raise HTTPException(status_code=403, detail="Operação financeira requer sessão institucional MFA AAL2.")


async def _institution(auth: AuthContext, db: AsyncSession):
    _require_staff(auth)
    try:
        payments.enabled()
    except payments.PaymentDenied as exc:
        raise HTTPException(status_code=503, detail="Pagamentos em sandbox não habilitados.") from exc
    await _require_ies(db, auth)


@router.get("/providers")
async def providers(
    auth: AuthContext = Depends(require_permission("settings.manage")),
    db: AsyncSession = Depends(get_db),
):
    await _institution(auth, db)
    rows = (await db.execute(select(PaymentProviderProfile).where(
        PaymentProviderProfile.tenant_id == auth.tenant_id,
    ).order_by(PaymentProviderProfile.created_at.desc()).limit(100))).scalars().all()
    return {"items": [_summary_provider(row) for row in rows], "multiple_providers": True}


@router.post("/providers", status_code=201)
async def register_provider(
    body: ProviderCreate,
    auth: AuthContext = Depends(require_permission("settings.manage")),
    db: AsyncSession = Depends(get_db),
):
    await _institution(auth, db)
    try:
        result = await payments.create_provider(
            db, tenant_id=auth.tenant_id, user_id=auth.user_id,
            source_id=str(body.finance_profile_id),
            name=body.name, kind=body.connection_kind,
            slug=body.provider_slug, methods=body.methods,
        )
        return _summary_provider(result)
    except payments.PaymentDenied as exc:
        await db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Provedor já cadastrado para esta origem.") from exc


@router.put("/providers/{provider_id}/sandbox-enable")
async def sandbox_enable(
    provider_id: UUID, body: ProviderEnable,
    auth: AuthContext = Depends(require_permission("settings.manage")),
    db: AsyncSession = Depends(get_db),
):
    await _institution(auth, db)
    try:
        result = await payments.change_provider_enabled(
            db, tenant_id=auth.tenant_id, provider_id=str(provider_id),
            expected_revision=body.expected_revision, value=body.enabled,
        )
        return _summary_provider(result)
    except payments.PaymentDenied as exc:
        await db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/drafts", status_code=201)
async def new_draft(
    body: PaymentDraftCreate,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=16, max_length=120),
    auth: AuthContext = Depends(require_permission("critical.manage")),
    db: AsyncSession = Depends(get_db),
):
    await _institution(auth, db)
    try:
        return await payments.create_draft(
            db, tenant_id=auth.tenant_id, user_id=auth.user_id,
            provider_id=str(body.provider_id), observation_id=str(body.financial_observation_id),
            method=body.method, idempotency_key=idempotency_key,
        )
    except payments.PaymentDenied as exc:
        await db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Chave de rascunho duplicada.") from exc


@router.get("/drafts")
async def list_drafts(
    auth: AuthContext = Depends(require_permission("students.sensitive.view")),
    db: AsyncSession = Depends(get_db),
):
    await _institution(auth, db)
    rows = (await db.execute(select(StudentPaymentIntent).where(
        StudentPaymentIntent.tenant_id == auth.tenant_id,
    ).order_by(StudentPaymentIntent.created_at.desc()).limit(100))).scalars().all()
    return {"items": [payments.describe_draft(row) for row in rows], "live_payments_enabled": False}


@router.get("/drafts/{draft_id}/events")
async def draft_events(
    draft_id: UUID,
    auth: AuthContext = Depends(require_permission("audit.view")),
    db: AsyncSession = Depends(get_db),
):
    await _institution(auth, db)
    draft = (await db.execute(select(StudentPaymentIntent.id).where(
        StudentPaymentIntent.tenant_id == auth.tenant_id,
        StudentPaymentIntent.id == str(draft_id),
    ))).scalar_one_or_none()
    if draft is None:
        raise HTTPException(status_code=404, detail="Rascunho não encontrado.")
    events = (await db.execute(select(StudentPaymentEvidence).where(
        StudentPaymentEvidence.tenant_id == auth.tenant_id,
        StudentPaymentEvidence.intent_id == str(draft_id),
    ).order_by(StudentPaymentEvidence.received_at.desc()).limit(100))).scalars().all()
    return {"items": [{
        "event_id": row.provider_event_id,
        "state_reported": row.reported_state,
        "amount_reported": str(row.reported_amount),
        "occurred_at": row.occurred_at.isoformat(),
    } for row in events], "settlement_confirmed": False, "evidence_source": "sandbox"}


@portal_router.get("/drafts")
async def student_drafts(
    identity: PortalIdentity = Depends(_portal_identity),
    db: AsyncSession = Depends(get_db),
):
    try:
        payments.enabled()
    except payments.PaymentDenied as exc:
        raise HTTPException(status_code=503, detail="Pagamentos em homologação.") from exc
    rows = (await db.execute(select(StudentPaymentIntent).where(
        StudentPaymentIntent.tenant_id == identity.tenant_id,
        StudentPaymentIntent.student_id == identity.student.id,
    ).order_by(StudentPaymentIntent.created_at.desc()).limit(50))).scalars().all()
    return {"items": [payments.describe_draft(row) for row in rows],
            "pay_now_available": False, "settlement_confirmed": False}


@sandbox_router.post("/{tenant_id}/{provider_id}", status_code=202)
async def sandbox_event(tenant_id: UUID, provider_id: UUID, request: Request):
    raw = await request.body()
    stamp = request.headers.get("X-MIRA-Sandbox-Timestamp", "")
    signature = request.headers.get("X-MIRA-Sandbox-Signature", "")
    try:
        # Pre-validate before opening a DB session or taking tenant context.
        payments.signed_sandbox_event(raw, stamp, signature, str(tenant_id), str(provider_id))
    except payments.PaymentDenied as exc:
        raise HTTPException(status_code=401, detail="Assinatura de homologação inválida ou desabilitada.") from exc
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        try:
            return await payments.store_sandbox_event(
                db, tenant_id=str(tenant_id), provider_id=str(provider_id),
                raw=raw, timestamp=stamp, signature=signature,
            )
        except payments.PaymentDenied as exc:
            await db.rollback()
            raise HTTPException(status_code=422, detail="Evento não corresponde ao contrato de homologação.") from exc
        except IntegrityError as exc:
            await db.rollback()
            raise HTTPException(status_code=409, detail="Evento concorrente duplicado.") from exc
