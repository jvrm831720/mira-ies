"""Fatura, plano e créditos de disparo por canal (MVP em memória por tenant)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.auth import AuthContext, require_min_role

router = APIRouter(prefix="/billing", tags=["Fatura e créditos"])

# Saldo em memória por tenant (MVP — depois migrar para tabela)
_STORE: dict[str, dict] = {}


def _default_state() -> dict:
    now = datetime.now(timezone.utc)
    return {
        "plan_name": "Mira Growth",
        "plan_status": "active",
        "plan_price_brl": 497.0,
        "billing_cycle": "monthly",
        "renews_at": (now + timedelta(days=22)).isoformat(),
        "next_invoice_brl": 497.0,
        "period_spend_brl": 126.0,
        "period_messages": 184,
        "credits": {"whatsapp": 850, "email": 2400, "sms": 320},
        "used_period": {"whatsapp": 120, "email": 310, "sms": 45},
    }


def _state_for(tenant_id: str) -> dict:
    if tenant_id not in _STORE:
        _STORE[tenant_id] = _default_state()
    return _STORE[tenant_id]


class PurchaseBody(BaseModel):
    channel: Literal["whatsapp", "email", "sms"]
    pack_id: str = Field(min_length=1, max_length=40)
    credits: int = Field(gt=0, le=100_000)


@router.get("/summary")
async def billing_summary(auth: AuthContext = Depends(require_min_role("viewer"))):
    return _state_for(auth.tenant_id)


@router.post("/credits")
async def purchase_credits(
    body: PurchaseBody,
    auth: AuthContext = Depends(require_min_role("admin")),
):
    state = _state_for(auth.tenant_id)
    state["credits"][body.channel] = int(state["credits"].get(body.channel, 0)) + body.credits
    # Aproxima gasto do período (MVP)
    unit = {"whatsapp": 0.12, "email": 0.03, "sms": 0.18}.get(body.channel, 0.1)
    state["period_spend_brl"] = round(float(state.get("period_spend_brl", 0)) + body.credits * unit, 2)
    return {
        "channel": body.channel,
        "added": body.credits,
        "balance": state["credits"][body.channel],
        "pack_id": body.pack_id,
    }
