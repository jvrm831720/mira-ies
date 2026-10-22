"""Fatura, plano e créditos por canal — valores configuráveis por tenant."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.auth import AuthContext, require_min_role

router = APIRouter(prefix="/billing", tags=["Fatura e créditos"])

# MVP em memória por tenant. Depois: tabela tenant_billing + invoices.
# Campos pensados para edição via banco / admin:
# plan_name, plan_price_brl, billing_cycle, payment_link, credits, invoices
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
        "payment_link": None,  # ex.: "https://pay.stripe.com/..." por cliente
        "credits": {"whatsapp": 850, "email": 2400, "sms": 320},
        "used_period": {"whatsapp": 120, "email": 310, "sms": 45},
        "invoices": [
            {
                "id": "inv-2026-10",
                "date": (now - timedelta(days=8)).date().isoformat(),
                "amount_brl": 497.0,
                "label": "Plano mensal · Outubro",
                "download_url": None,
            },
            {
                "id": "inv-2026-09",
                "date": (now - timedelta(days=38)).date().isoformat(),
                "amount_brl": 497.0,
                "label": "Plano mensal · Setembro",
                "download_url": None,
            },
            {
                "id": "inv-2026-08",
                "date": (now - timedelta(days=68)).date().isoformat(),
                "amount_brl": 447.0,
                "label": "Plano mensal · Agosto",
                "download_url": None,
            },
        ],
    }


def _state_for(tenant_id: str) -> dict:
    if tenant_id not in _STORE:
        _STORE[tenant_id] = _default_state()
    return _STORE[tenant_id]


class PurchaseBody(BaseModel):
    channel: Literal["whatsapp", "email", "sms"]
    pack_id: str = Field(min_length=1, max_length=40)
    credits: int = Field(gt=0, le=100_000)


class PlanUpdateBody(BaseModel):
    """Atualização admin do plano do tenant (base para edição via painel/DB)."""

    plan_name: str | None = Field(default=None, min_length=2, max_length=120)
    plan_price_brl: float | None = Field(default=None, ge=0)
    billing_cycle: Literal["monthly", "yearly"] | None = None
    payment_link: str | None = Field(default=None, max_length=500)
    renews_at: str | None = None
    next_invoice_brl: float | None = Field(default=None, ge=0)


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
    unit = {"whatsapp": 0.12, "email": 0.03, "sms": 0.18}.get(body.channel, 0.1)
    state["period_spend_brl"] = round(float(state.get("period_spend_brl", 0)) + body.credits * unit, 2)
    return {
        "channel": body.channel,
        "added": body.credits,
        "balance": state["credits"][body.channel],
        "pack_id": body.pack_id,
    }


@router.patch("/plan")
async def update_plan(
    body: PlanUpdateBody,
    auth: AuthContext = Depends(require_min_role("admin")),
):
    """Permite ajustar plano/preço/link por instituição (MVP em memória)."""
    state = _state_for(auth.tenant_id)
    data = body.model_dump(exclude_unset=True)
    for key, value in data.items():
        if value is not None or key == "payment_link":
            state[key] = value
    if "plan_price_brl" in data and data["plan_price_brl"] is not None and "next_invoice_brl" not in data:
        state["next_invoice_brl"] = data["plan_price_brl"]
    return state
