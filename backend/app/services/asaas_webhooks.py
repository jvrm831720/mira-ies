"""Authenticated Asaas webhooks: persist first, then process in retryable worker.

The shared issuer receives all tenants through a single URL. A narrowly scoped
transaction-local SQL lookup resolves payment ID to tenant, never a user field.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.asaas_live import AsaasWebhookEvent, AsaasWebhookApplication
from app.services import asaas_gateway as gateway
from app.services.asaas_live import reconcile_charge, AsaasFlowDenied
from app.services.dispatch_core import bind_tenant

_EVENT = re.compile(r"^[A-Za-z0-9_&-]{5,120}$")
_PAYMENT = re.compile(r"^pay_[A-Za-z0-9_-]{4,72}$")
_TYPE = re.compile(r"^PAYMENT_[A-Z_]{2,72}$")
_SPLIT_ID = re.compile(r"^[A-Za-z0-9_-]{6,100}$")


class AsaasHookDenied(ValueError):
    pass


def valid_token(value: str | None) -> None:
    expected = gateway.token()
    if not isinstance(value, str) or not hmac.compare_digest(value, expected):
        raise AsaasHookDenied("Autenticação Asaas inválida.")


def parse_event(body: bytes) -> dict:
    if not isinstance(body, bytes) or not 2 <= len(body) <= 32768:
        raise AsaasHookDenied("Tamanho de evento inválido.")
    try:
        event = json.loads(body)
    except (ValueError, UnicodeError) as exc:
        raise AsaasHookDenied("Evento JSON inválido.") from exc
    if not isinstance(event, dict) or not isinstance(event.get("payment"), dict):
        raise AsaasHookDenied("Envelope de evento incompatível.")
    eid, etype, payment = event.get("id"), event.get("event"), event["payment"].get("id")
    if not isinstance(eid, str) or not _EVENT.fullmatch(eid):
        raise AsaasHookDenied("ID de evento inválido.")
    if not isinstance(etype, str) or not _TYPE.fullmatch(etype):
        raise AsaasHookDenied("Tipo de evento inválido.")
    if not isinstance(payment, str) or not _PAYMENT.fullmatch(payment):
        raise AsaasHookDenied("ID de cobrança inválido.")
    info = event.get("additionalInfo") or {}
    if not isinstance(info, dict):
        raise AsaasHookDenied("Dados extras inválidos.")
    split_id = info.get("splitId")
    if split_id is not None and (not isinstance(split_id, str) or not _SPLIT_ID.fullmatch(split_id)):
        raise AsaasHookDenied("Identificador de split inválido.")
    return {"event_id": eid, "event_type": etype,
            "payment_id": payment, "split_id": split_id,
            "sha256": hashlib.sha256(body).hexdigest()}


async def ingest(db: AsyncSession, *, raw: bytes, token: str) -> dict:
    # Validate token BEFORE database RLS lookup, logging and parsing.
    valid_token(token)
    event = parse_event(raw)
    await db.execute(text("SELECT set_config('app.asaas_webhook_authenticated', 'yes', true)"))
    lookup = (await db.execute(text(
        "SELECT resolved_tenant, resolved_charge FROM mira_asaas_resolve_payment(:id)"
    ), {"id": event["payment_id"]})).first()
    if lookup is None:
        # A matching charge can arrive shortly after the provider accepted its
        # creation; return retryable 503 rather than silently dropping evidence.
        raise AsaasHookDenied("Cobrança ainda não mapeada; retry do provedor necessário.")
    tenant_id, charge_id = str(lookup[0]), str(lookup[1])
    await bind_tenant(db, tenant_id)
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:id,0))"),
                     {"id": "asaas:webhook:" + event["event_id"]})
    existing = (await db.execute(select(AsaasWebhookEvent).where(
        AsaasWebhookEvent.tenant_id == tenant_id,
        AsaasWebhookEvent.event_id == event["event_id"],
    ))).scalar_one_or_none()
    if existing is not None:
        if existing.payload_sha256 != event["sha256"] or existing.payment_id != event["payment_id"]:
            raise AsaasHookDenied("Reuso de ID de evento com conteúdo diferente.")
        return {"received": True, "duplicate": True, "tenant_id": tenant_id}
    db.add(AsaasWebhookEvent(
        tenant_id=tenant_id, charge_id=charge_id,
        event_id=event["event_id"], event_type=event["event_type"],
        payment_id=event["payment_id"], split_id=event["split_id"],
        payload_sha256=event["sha256"],
    ))
    await db.commit()
    return {"received": True, "duplicate": False, "tenant_id": tenant_id}


async def work_tenant(db: AsyncSession, tenant_id: str, *, limit: int = 20) -> dict:
    gateway.environment()
    if not 1 <= limit <= 50:
        raise AsaasHookDenied("Limite de processamento inválido.")
    await bind_tenant(db, tenant_id)
    events = (await db.execute(
        select(AsaasWebhookEvent)
        .outerjoin(
            AsaasWebhookApplication,
            (AsaasWebhookApplication.tenant_id == AsaasWebhookEvent.tenant_id)
            & (AsaasWebhookApplication.event_id == AsaasWebhookEvent.id),
        )
        .where(AsaasWebhookEvent.tenant_id == tenant_id, AsaasWebhookApplication.id.is_(None))
        .order_by(AsaasWebhookEvent.received_at, AsaasWebhookEvent.id)
        .limit(limit)
    )).scalars().all()
    processed, pending = 0, 0
    for event in events:
        await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:id,0))"),
                         {"id": "asaas:worker:" + tenant_id + ":" + event.id})
        exists = (await db.execute(select(AsaasWebhookApplication.id).where(
            AsaasWebhookApplication.tenant_id == tenant_id,
            AsaasWebhookApplication.event_id == event.id,
        ))).scalar_one_or_none()
        if exists is not None:
            await db.commit()
            continue
        # Always re-read provider state; delivery order may differ from event time.
        try:
            latest = await reconcile_charge(db, tenant_id=tenant_id, charge_id=event.charge_id)
        except (AsaasFlowDenied, gateway.GatewayInconclusive, gateway.GatewayRejected):
            await db.rollback()
            pending += 1
            continue
        db.add(AsaasWebhookApplication(
            tenant_id=tenant_id, event_id=event.id, outcome="reconciled",
            provider_status=latest["payment_status"],
        ))
        await db.commit()
        processed += 1
    return {"processed": processed, "remaining_or_failed": pending,
            "scope": tenant_id, "side_effects": "provider_read_only"}


def worker_secret_valid(value: str | None) -> None:
    secret = get_settings().asaas_worker_secret
    if not isinstance(secret, str) or len(secret) < 32 or not isinstance(value, str):
        raise AsaasHookDenied("Worker não habilitado.")
    if not hmac.compare_digest(secret, value):
        raise AsaasHookDenied("Worker não autorizado.")
