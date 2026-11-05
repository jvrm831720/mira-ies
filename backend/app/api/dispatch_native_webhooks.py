"""Native provider webhooks: reject unsigned delivery status, never infer tenant.

Official Resend Svix and Twilio SDK validators are used. These routes are
independent from the internal HMAC gateway (kept for verified custom providers).
"""
from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request

from app.core.config import get_settings
from app.api.dispatch_integrations import VerifiedGatewayEvent, ingest_verified_event

router = APIRouter(prefix="/dispatch/native", tags=["Verified Provider Webhooks"])


def _parse_tenant(tenant_id: str) -> str:
    try:
        return str(UUID(tenant_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Destino inválido.") from exc


def _require_bytes(raw: bytes) -> None:
    if len(raw) > 32768:
        raise HTTPException(status_code=413, detail="Evento maior que o limite.")


def verify_resend_signature(raw: bytes, headers: dict[str, str], secret: str) -> None:
    """Official Svix signature+timestamp validation; never parse JSON first."""
    from svix.webhooks import Webhook
    try:
        Webhook(secret).verify(raw.decode("utf-8"), headers)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Webhook Resend inválido.") from exc


@router.post("/resend/{tenant_id}")
async def resend_events(tenant_id: str, request: Request):
    tenant = _parse_tenant(tenant_id)
    raw = await request.body()
    _require_bytes(raw)
    settings = get_settings()
    if not settings.dispatch_resend_webhook_secret:
        raise HTTPException(status_code=503, detail="Webhook Resend não configurado.")
    headers = {key: request.headers.get(key) or "" for key in
               ("svix-id", "svix-timestamp", "svix-signature")}
    if not all(headers.values()):
        raise HTTPException(status_code=401, detail="Assinatura ausente.")
    verify_resend_signature(raw, headers, settings.dispatch_resend_webhook_secret)

    try:
        payload: dict[str, Any] = json.loads(raw)
        event_type = payload.get("type", "")
        provider_id = payload.get("data", {}).get("email_id")
    except (ValueError, AttributeError, TypeError) as exc:
        raise HTTPException(status_code=422, detail="Formato de webhook inválido.") from exc

    kinds = {
        "email.delivered": "delivered",
        "email.opened": "read",
        "email.bounced": "failed",
        "email.complained": "failed",
        "email.suppressed": "failed",
        "email.failed": "failed",
    }
    kind = kinds.get(event_type)
    if not kind:
        return {"accepted": True, "ignored": True}
    if not isinstance(provider_id, str) or len(provider_id)>200:
        raise HTTPException(status_code=422, detail="Identificador de envio inválido.")
    event = VerifiedGatewayEvent(
        tenant_id=tenant,
        provider_message_id=provider_id,
        external_event_id=headers["svix-id"][:180],
        kind=kind,
        # Signals originate from the signed provider, not user-supplied messages.
        message=event_type,
    )
    return await ingest_verified_event(provider="resend", event=event, raw=raw)


@router.post("/twilio/{tenant_id}")
async def twilio_events(tenant_id: str, request: Request):
    tenant = _parse_tenant(tenant_id)
    raw = await request.body()
    _require_bytes(raw)
    settings = get_settings()
    url = settings.dispatch_twilio_callback_url
    if not settings.twilio_auth_token or not settings.twilio_account_sid or not url:
        raise HTTPException(status_code=503, detail="Webhook Twilio não configurado.")
    # The URL is configured and pinned to the provider, never built from
    # untrusted Host/X-Forwarded-* headers.
    if not url.startswith("https://") or not url.endswith(f"/dispatch/native/twilio/{tenant}"):
        raise HTTPException(status_code=503, detail="StatusCallback não corresponde ao tenant.")
    content_type = request.headers.get("content-type", "").lower()
    if not content_type.startswith("application/x-www-form-urlencoded"):
        raise HTTPException(status_code=415, detail="Tipo de evento Twilio não aceito.")
    from urllib.parse import parse_qsl
    try:
        params = dict(parse_qsl(raw.decode("utf-8"), keep_blank_values=True, strict_parsing=True))
    except (UnicodeDecodeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Parâmetros inválidos.") from exc
    from twilio.request_validator import RequestValidator
    validator = RequestValidator(settings.twilio_auth_token)
    signature = request.headers.get("X-Twilio-Signature") or ""
    if not signature or not validator.validate(url, params, signature):
        raise HTTPException(status_code=401, detail="Assinatura Twilio inválida.")
    if params.get("AccountSid") != settings.twilio_account_sid:
        raise HTTPException(status_code=401, detail="Conta Twilio incompatível.")

    kinds = {
        "delivered": "delivered",
        "read": "read",
        "failed": "failed",
        "undelivered": "failed",
    }
    kind = kinds.get(params.get("MessageStatus", "").lower())
    if not kind:
        return {"accepted": True, "ignored": True}
    sid = params.get("MessageSid") or params.get("SmsSid")
    if not sid or len(sid) > 200:
        raise HTTPException(status_code=422, detail="Identificador de mensagem inválido.")
    event = VerifiedGatewayEvent(
        tenant_id=tenant, provider_message_id=sid,
        # Twilio has no stable event-id in every callback: exact signed payload hash
        # deduplicates retries, and later status changes still have a new hash.
        external_event_id=hashlib.sha256(raw).hexdigest(),
        kind=kind, message=params.get("MessageStatus"),
    )
    return await ingest_verified_event(provider="twilio", event=event, raw=raw)
