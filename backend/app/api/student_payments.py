"""Wave 4D-A institutional payment preparation. No payment execution endpoint."""
from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.native_academic import _require_ies
from app.core.auth import AuthContext, require_permission
from app.db.session import get_db
from app.models.student_payments import StudentPaymentConnector, StudentPaymentOrder, StudentPaymentOrderEvent
from app.services import student_payments as engine

router = APIRouter(prefix="/native-academic/finance/payments", tags=["Student payment preparation"])


def _actor(auth: AuthContext) -> str:
    if not auth.user_id or not auth.session_id or auth.aal < 2:
        raise HTTPException(status_code=403, detail="Ações financeiras exigem MFA AAL2.")
    return auth.user_id


async def _institution(auth: AuthContext, db: AsyncSession):
    _actor(auth)
    try:
        engine.require_enabled()
    except engine.PaymentPreparationDenied as exc:
        raise HTTPException(status_code=503, detail="Pagamentos estão em homologação.") from exc
    await _require_ies(db, auth)


def _connector_json(connector: StudentPaymentConnector) -> dict:
    return {
        "id": connector.id, "name": connector.name,
        "provider_slug": "asaas",
        "destination_wallet_id": connector.destination_wallet_id,
        "destination_verification_status": connector.destination_verification_status,
        "split_percentual_value": 100,
        "split_basis": "netValue",
        "finance_profile_id": connector.finance_profile_id,
        "mode": connector.mode, "enabled": connector.enabled,
        "configuration_version": connector.configuration_version,
        "payment_execution_enabled": False,
    }


class CreateConnector(BaseModel):
    destination_wallet_id: UUID
    finance_profile_id: UUID


class UpdateConnector(BaseModel):
    expected_version: int = Field(ge=1)
    enabled: bool


class PrepareOrder(BaseModel):
    connector_id: UUID
    observation_id: UUID


class ReviewOrder(BaseModel):
    expected_status: Literal["draft", "awaiting_approval", "approved"]
    target: Literal["awaiting_approval", "approved", "cancelled"]
    note: str = Field(min_length=5, max_length=500)


@router.get("/connectors")
async def connectors(
    auth: AuthContext = Depends(require_permission("settings.manage")),
    db: AsyncSession = Depends(get_db),
):
    await _institution(auth, db)
    rows = (await db.execute(select(StudentPaymentConnector).where(
        StudentPaymentConnector.tenant_id == auth.tenant_id,
    ).order_by(StudentPaymentConnector.created_at.desc()).limit(100))).scalars().all()
    return {"items": [_connector_json(x) for x in rows],
            "multiple_sources_supported": True, "live_enabled": False}


@router.post("/connectors", status_code=201)
async def create_connector(
    body: CreateConnector,
    auth: AuthContext = Depends(require_permission("settings.manage")),
    db: AsyncSession = Depends(get_db),
):
    await _institution(auth, db)
    try:
        row = await engine.create_connector(
            db, tenant_id=auth.tenant_id, actor_id=auth.user_id,
            destination_wallet_id=str(body.destination_wallet_id),
            finance_profile_id=str(body.finance_profile_id),
        )
        return _connector_json(row)
    except engine.PaymentPreparationDenied as exc:
        await db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Nome de conector já utilizado.") from exc


@router.put("/connectors/{connector_id}")
async def toggle_connector(
    connector_id: UUID, body: UpdateConnector,
    auth: AuthContext = Depends(require_permission("settings.manage")),
    db: AsyncSession = Depends(get_db),
):
    await _institution(auth, db)
    try:
        row = await engine.toggle_connector(
            db, tenant_id=auth.tenant_id, connector_id=str(connector_id),
            expected_version=body.expected_version, enabled=body.enabled,
        )
        return _connector_json(row)
    except engine.PaymentPreparationDenied as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/orders")
async def orders(
    limit: int = Query(default=50, ge=1, le=100),
    auth: AuthContext = Depends(require_permission("students.sensitive.view")),
    db: AsyncSession = Depends(get_db),
):
    await _institution(auth, db)
    rows = (await db.execute(select(StudentPaymentOrder).where(
        StudentPaymentOrder.tenant_id == auth.tenant_id,
    ).order_by(StudentPaymentOrder.created_at.desc()).limit(limit))).scalars().all()
    return {"items": [engine.order_json(x) for x in rows],
            "payment_execution_enabled": False, "settlement_confirmed": False}


@router.post("/orders", status_code=201)
async def prepare_order(
    body: PrepareOrder,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=16, max_length=120),
    auth: AuthContext = Depends(require_permission("critical.manage")),
    db: AsyncSession = Depends(get_db),
):
    await _institution(auth, db)
    try:
        order, deduplicated = await engine.prepare_order(
            db, tenant_id=auth.tenant_id, actor_id=auth.user_id,
            connector_id=str(body.connector_id), observation_id=str(body.observation_id),
            idempotency_key=idempotency_key,
        )
        return {**engine.order_json(order), "deduplicated": deduplicated}
    except engine.PaymentPreparationDenied as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Proposta duplicada ou concorrente.") from exc


@router.post("/orders/{order_id}/review")
async def review_order(
    order_id: UUID, body: ReviewOrder,
    auth: AuthContext = Depends(require_permission("critical.manage")),
    db: AsyncSession = Depends(get_db),
):
    await _institution(auth, db)
    try:
        order = await engine.transition_order(
            db, tenant_id=auth.tenant_id, order_id=str(order_id), actor_id=auth.user_id,
            target=body.target, expected_status=body.expected_status, note=body.note,
        )
        return engine.order_json(order)
    except engine.PaymentPreparationDenied as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/orders/{order_id}/history")
async def order_history(
    order_id: UUID,
    auth: AuthContext = Depends(require_permission("audit.view")),
    db: AsyncSession = Depends(get_db),
):
    await _institution(auth, db)
    row = (await db.execute(select(StudentPaymentOrder).where(
        StudentPaymentOrder.tenant_id == auth.tenant_id,
        StudentPaymentOrder.id == str(order_id),
    ))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Proposta não encontrada.")
    events = (await db.execute(select(StudentPaymentOrderEvent).where(
        StudentPaymentOrderEvent.tenant_id == auth.tenant_id,
        StudentPaymentOrderEvent.order_id == str(order_id),
    ).order_by(StudentPaymentOrderEvent.occurred_at))).scalars().all()
    return {"order_id": row.id, "events": [{
        "status": e.status, "actor_id": e.actor_id, "note": e.note,
        "occurred_at": e.occurred_at.isoformat(),
    } for e in events], "settlement_confirmed": False}


@router.post("/orders/{order_id}/execute", status_code=503)
async def execute_unavailable(
    order_id: UUID,
    auth: AuthContext = Depends(require_permission("critical.manage")),
    db: AsyncSession = Depends(get_db),
):
    await _institution(auth, db)
    raise HTTPException(status_code=503, detail="Execução real exige adaptador PSP homologado e liberação operacional.")
