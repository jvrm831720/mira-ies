"""Endpoints públicos para callbacks de entrega, protegidos por HMAC do tenant."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_webhook_signature
from app.db.session import get_db
from app.models.tenant import Tenant
from app.services.delivery_webhooks import apply_delivery_event, normalize_delivery_event

router = APIRouter()
_VALID_PROVIDERS = {"evolution", "resend", "twilio", "whatsapp", "email", "sms"}


@router.post("/agents/webhooks/{provider}/{tenant_id}")
async def receive_delivery_webhook(
    provider: str,
    tenant_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    provider = provider.lower().strip()
    if provider not in _VALID_PROVIDERS:
        raise HTTPException(status_code=404, detail="Provider de webhook não suportado")

    tenant = await db.get(Tenant, tenant_id)
    if not tenant or not tenant.is_active:
        raise HTTPException(status_code=404, detail="Tenant não encontrado")

    raw_body = await request.body()
    signature = request.headers.get("X-Beacon-Signature")
    if not verify_webhook_signature(raw_body, signature, tenant.webhook_secret):
        raise HTTPException(status_code=401, detail="Assinatura de webhook inválida")

    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Payload JSON inválido") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail="Payload de webhook deve ser um objeto JSON")

    event = normalize_delivery_event(provider, payload)
    if not event:
        raise HTTPException(status_code=422, detail="Status de entrega não reconhecido")
    return await apply_delivery_event(db, tenant_id=tenant_id, event=event)
