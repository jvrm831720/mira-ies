"""Official Asaas institutional API, student payment instructions and provider webhook.

No frontend-supplied amounts, API URLs, split recipients or provider credentials.
"""
from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.native_academic import PortalIdentity, _portal_identity, _require_ies
from app.core.auth import AuthContext, require_permission
from app.db.session import AsyncSessionLocal, get_db
from app.models.asaas_live import AsaasCharge, AsaasWebhookEvent
from app.services import asaas_gateway as gateway
from app.services import asaas_live as flow
from app.services import asaas_webhooks as hooks
from app.services.dispatch_core import bind_tenant

router = APIRouter(prefix="/native-academic/finance/asaas", tags=["Asaas official payments"])
portal = APIRouter(prefix="/student-portal/services/asaas", tags=["Asaas student payment instructions"])
incoming = APIRouter(prefix="/webhooks/asaas", tags=["Asaas verified webhook"])


class PrepareCharge(BaseModel):
    model_config = ConfigDict(extra="forbid")
    financial_observation_id: UUID
    method: str = Field(pattern="^(pix|boleto)$")
    due_date: date


class ConfirmCharge(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirms_issue: bool


class ReviewWallet(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evidence_reference: str = Field(min_length=8, max_length=120, pattern="^[A-Za-z0-9_-]+$")


def _human(auth: AuthContext) -> None:
    if not auth.user_id or not auth.session_id or auth.aal < 2:
        raise HTTPException(status_code=403, detail="Requer MFA e sessão institucional.")


async def _institution(auth: AuthContext, db: AsyncSession):
    _human(auth)
    try:
        gateway.environment()
    except gateway.GatewayDenied as exc:
        raise HTTPException(status_code=503, detail="Integração oficial Asaas ainda não habilitada.") from exc
    await _require_ies(db, auth)


def _error(exc: Exception, *, status: int = 422):
    if isinstance(exc, (gateway.GatewayInconclusive, gateway.GatewayRejected)):
        return HTTPException(status_code=503, detail="Provedor Asaas indisponível ou operação inconclusiva.")
    if isinstance(exc, gateway.GatewayDenied):
        return HTTPException(status_code=503, detail="Provedor Asaas não habilitado.")
    return HTTPException(status_code=status, detail=str(exc))


@router.get("/health")
async def readiness(
    auth: AuthContext = Depends(require_permission("settings.manage")),
    db: AsyncSession = Depends(get_db),
):
    _human(auth)
    await _require_ies(db, auth)
    try:
        mode = gateway.environment()
        return {"enabled": True, "environment": mode,
                "production": mode == "production",
                "split_percent_of_net": 100, "live_issuer_authorized": mode == "production"}
    except gateway.GatewayDenied:
        return {"enabled": False, "environment": "disabled", "production": False}


@router.post("/destination/verify")
async def verify_wallet(
    body: ReviewWallet,
    auth: AuthContext = Depends(require_permission("critical.manage")),
    db: AsyncSession = Depends(get_db),
):
    await _institution(auth, db)
    try:
        return await flow.verify_destination(
            db, tenant_id=auth.tenant_id, reviewer_id=auth.user_id,
            evidence_reference=body.evidence_reference,
        )
    except flow.AsaasFlowDenied as exc:
        await db.rollback()
        raise _error(exc) from exc


@router.post("/charges/prepare", status_code=201)
async def prepare(
    body: PrepareCharge,
    auth: AuthContext = Depends(require_permission("critical.manage")),
    db: AsyncSession = Depends(get_db),
):
    await _institution(auth, db)
    try:
        return await flow.prepare_charge(
            db, tenant_id=auth.tenant_id, user_id=auth.user_id,
            observation_id=str(body.financial_observation_id),
            method=body.method, due_date=body.due_date,
        )
    except (flow.AsaasFlowDenied, gateway.GatewayDenied,
            gateway.GatewayInconclusive, gateway.GatewayRejected) as exc:
        await db.rollback()
        raise _error(exc) from exc
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Esta obrigação já possui uma cobrança.") from exc


@router.post("/charges/{charge_id}/issue")
async def issue(
    charge_id: UUID, body: ConfirmCharge,
    auth: AuthContext = Depends(require_permission("critical.manage")),
    db: AsyncSession = Depends(get_db),
):
    await _institution(auth, db)
    if not body.confirms_issue:
        raise HTTPException(status_code=422, detail="Confirmação explícita obrigatória.")
    try:
        return await flow.submit_charge(
            db, tenant_id=auth.tenant_id, charge_id=str(charge_id),
            user_id=auth.user_id,
        )
    except (flow.AsaasFlowDenied, gateway.GatewayDenied,
            gateway.GatewayInconclusive, gateway.GatewayRejected) as exc:
        await db.rollback()
        raise _error(exc, status=409) from exc


@router.post("/charges/{charge_id}/reconcile")
async def reconcile(
    charge_id: UUID,
    auth: AuthContext = Depends(require_permission("critical.manage")),
    db: AsyncSession = Depends(get_db),
):
    await _institution(auth, db)
    try:
        return await flow.reconcile_charge(db, tenant_id=auth.tenant_id, charge_id=str(charge_id))
    except (flow.AsaasFlowDenied, gateway.GatewayDenied,
            gateway.GatewayInconclusive, gateway.GatewayRejected) as exc:
        await db.rollback()
        raise _error(exc, status=409) from exc


@router.get("/charges")
async def charges(
    auth: AuthContext = Depends(require_permission("students.sensitive.view")),
    db: AsyncSession = Depends(get_db),
):
    await _institution(auth, db)
    await bind_tenant(db, auth.tenant_id)
    rows = (await db.execute(select(AsaasCharge).where(
        AsaasCharge.tenant_id == auth.tenant_id,
    ).order_by(AsaasCharge.created_at.desc()).limit(100))).scalars().all()
    return {"items": [flow.present(row) for row in rows], "provider": "asaas"}


@router.get("/webhook-events")
async def webhook_events(
    auth: AuthContext = Depends(require_permission("audit.view")),
    db: AsyncSession = Depends(get_db),
):
    await _institution(auth, db)
    await bind_tenant(db, auth.tenant_id)
    events = (await db.execute(select(AsaasWebhookEvent).where(
        AsaasWebhookEvent.tenant_id == auth.tenant_id,
    ).order_by(AsaasWebhookEvent.received_at.desc()).limit(100))).scalars().all()
    return {"items": [
        {"event_id": e.event_id, "event_type": e.event_type,
         "charge_id": e.charge_id, "received_at": e.received_at.isoformat()}
        for e in events
    ]}


@portal.get("/charges")
async def student_charges(
    identity: PortalIdentity = Depends(_portal_identity),
    db: AsyncSession = Depends(get_db),
):
    try:
        gateway.environment()
    except gateway.GatewayDenied as exc:
        raise HTTPException(status_code=503, detail="Pagamento indisponível.") from exc
    await bind_tenant(db, identity.tenant_id)
    items = (await db.execute(select(AsaasCharge).where(
        AsaasCharge.tenant_id == identity.tenant_id,
        AsaasCharge.student_id == identity.student.id,
        AsaasCharge.creation_state == "created",
    ).order_by(AsaasCharge.created_at.desc()).limit(50))).scalars().all()
    return {"items": [flow.present(item) for item in items]}


@portal.get("/charges/{charge_id}/instructions")
async def student_instructions(
    charge_id: UUID, identity: PortalIdentity = Depends(_portal_identity),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await flow.issue_payment_instructions(
            db, tenant_id=identity.tenant_id,
            student_id=identity.student.id, charge_id=str(charge_id),
        )
    except (flow.AsaasFlowDenied, gateway.GatewayDenied,
            gateway.GatewayInconclusive, gateway.GatewayRejected) as exc:
        raise _error(exc, status=404) from exc


@incoming.post("/payments")
async def incoming_webhook(request: Request):
    # Shared issuer webhook: never accept tenant ID from payload or path.
    token = request.headers.get("asaas-access-token", "")
    try:
        hooks.valid_token(token)
    except (hooks.AsaasHookDenied, gateway.GatewayDenied) as exc:
        raise HTTPException(status_code=401, detail="Webhook não autorizado.") from exc
    data = bytearray()
    async for piece in request.stream():
        data.extend(piece)
        if len(data) > 32768:
            raise HTTPException(status_code=413, detail="Webhook acima do limite.")
    async with AsyncSessionLocal() as db:
        try:
            result = await hooks.ingest(db, raw=bytes(data), token=token)
            return {"received": result["received"], "duplicate": result["duplicate"]}
        except hooks.AsaasHookDenied as exc:
            await db.rollback()
            # Unknown payment IDs are retryable, not accepted or silently lost.
            if "ainda não mapeada" in str(exc):
                raise HTTPException(status_code=503, detail="Cobrança ainda não registrada.") from exc
            raise HTTPException(status_code=422, detail="Evento Asaas inválido.") from exc
        except IntegrityError as exc:
            await db.rollback()
            raise HTTPException(status_code=503, detail="Evento concorrente deve ser reenviado.") from exc


@incoming.post("/worker/{tenant_id}")
async def process_tenant(
    tenant_id: UUID,
    worker_secret: str = Header(..., alias="X-MIRA-Asaas-Worker-Secret"),
):
    try:
        hooks.worker_secret_valid(worker_secret)
        async with AsyncSessionLocal() as db:
            return await hooks.work_tenant(db, str(tenant_id))
    except (hooks.AsaasHookDenied, gateway.GatewayDenied) as exc:
        raise HTTPException(status_code=401, detail="Worker não autorizado ou desabilitado.") from exc
