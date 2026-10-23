"""Normalização de webhooks de entrega dos canais de comunicação."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.intervention import InterventionLog
from app.models.student import Student
from app.services.consent import CHANNELS, apply_preference_changes
from app.services.engagement import record_engagement_event


DELIVERY_STATUSES = {
    "queued",
    "submitted",
    "delivered",
    "read",
    "failed",
    "rejected",
    "bounced",
    "invalid",
    "opted_out",
}

_TERMINAL_FAILURES = {"failed", "rejected", "bounced", "invalid"}


@dataclass(frozen=True)
class DeliveryEvent:
    provider: str
    status: str
    event_id: str
    external_id: str | None = None
    idempotency_key: str | None = None
    occurred_at: datetime | None = None


def _nested(payload: dict[str, Any], *paths: tuple[str, ...]) -> Any:
    for path in paths:
        value: Any = payload
        for key in path:
            if not isinstance(value, dict) or key not in value:
                value = None
                break
            value = value[key]
        if value not in (None, ""):
            return value
    return None


def _normalize_status(raw: Any) -> str | None:
    if raw is None:
        return None
    value = str(raw).strip().lower().replace(".", "_").replace("-", "_")
    if "opt" in value or value in {
        "unsubscribe",
        "unsubscribed",
        "stop",
        "parar",
        "sair",
        "nao quero receber",
        "não quero receber",
    }:
        return "opted_out"
    if value in {"read", "seen", "opened", "open"} or "read" in value:
        return "read"
    if "deliver" in value:
        return "delivered"
    if "bounce" in value:
        return "bounced"
    if "reject" in value:
        return "rejected"
    if value in {"invalid", "undeliverable", "unreachable"}:
        return "invalid"
    if value in {"failed", "failure", "error", "undelivered", "canceled", "cancelled"}:
        return "failed"
    if value in {"queued", "pending", "accepted", "sent", "submitted", "processing"}:
        return "submitted"
    return None


def _status_from_payload(payload: dict[str, Any]) -> str | None:
    paths = (
        ("status",),
        ("MessageStatus",),
        ("message_status",),
        ("data", "status"),
        ("data", "MessageStatus"),
        ("data", "message_status"),
        ("Body",),
        ("body",),
        ("data", "Body"),
        ("data", "body"),
        ("event",),
        ("type",),
        ("data", "event"),
        ("data", "type"),
    )
    for path in paths:
        status = _normalize_status(_nested(payload, path))
        if status:
            return status
    return None


def _parse_event_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    try:
        if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()):
            raw = float(value)
            if raw > 10_000_000_000:
                raw /= 1000.0
            return datetime.fromtimestamp(raw, tz=timezone.utc)
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def normalize_delivery_event(provider: str, payload: dict[str, Any]) -> DeliveryEvent | None:
    provider = provider.lower().strip()
    status = _status_from_payload(payload)
    if not status:
        return None

    external_id = _nested(
        payload,
        ("external_id",),
        ("message_id",),
        ("messageId",),
        ("MessageSid",),
        ("message_sid",),
        ("data", "external_id"),
        ("data", "email_id"),
        ("data", "message_id"),
        ("data", "key", "id"),
    )
    idempotency_key = _nested(
        payload,
        ("idempotency_key",),
        ("metadata", "idempotency_key"),
        ("data", "idempotency_key"),
        ("data", "metadata", "idempotency_key"),
    )
    raw_event_id = _nested(
        payload,
        ("event_id",),
        ("eventId",),
        ("data", "event_id"),
    )
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    if raw_event_id and str(raw_event_id) != str(external_id):
        event_id = str(raw_event_id)
    else:
        # Alguns providers repetem o message id em todos os callbacks; o hash
        # do payload mantém delivered/read como eventos distintos.
        event_id = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    occurred_at = _parse_event_datetime(
        _nested(
            payload,
            ("occurred_at",),
            ("timestamp",),
            ("created_at",),
            ("date",),
            ("data", "timestamp"),
            ("data", "created_at"),
        )
    )
    return DeliveryEvent(
        provider=provider,
        status=status,
        event_id=event_id[:160],
        external_id=str(external_id)[:120] if external_id else None,
        idempotency_key=str(idempotency_key)[:255] if idempotency_key else None,
        occurred_at=occurred_at,
    )


async def apply_delivery_event(
    session: AsyncSession,
    *,
    tenant_id: str,
    event: DeliveryEvent,
) -> dict[str, Any]:
    """Atualiza no máximo um log; eventos duplicados/out-of-order são inofensivos."""
    query = select(InterventionLog).where(InterventionLog.tenant_id == tenant_id)
    if event.external_id:
        query = query.where(InterventionLog.external_id == event.external_id)
    elif event.idempotency_key:
        query = query.where(InterventionLog.idempotency_key == event.idempotency_key)
    else:
        return {"updated": False, "reason": "missing_message_identifier", "status": event.status}
    query = query.order_by(InterventionLog.created_at.desc()).limit(1)
    log = (await session.execute(query)).scalar_one_or_none()
    if not log:
        return {"updated": False, "reason": "message_not_found", "status": event.status}
    if log.delivery_event_id == event.event_id:
        return {"updated": False, "duplicate": True, "log_id": log.id, "status": log.delivery_status}

    current = log.delivery_status
    if current == "read" and event.status != "read":
        return {"updated": False, "stale": True, "log_id": log.id, "status": current}
    if current == "delivered" and event.status in {"queued", "submitted", "failed"}:
        return {"updated": False, "stale": True, "log_id": log.id, "status": current}

    log.delivery_status = event.status
    log.delivery_event_id = event.event_id
    log.delivery_updated_at = datetime.now(timezone.utc)
    if event.status == "opted_out" and log.student_id:
        student_result = await session.execute(
            select(Student).where(
                Student.id == log.student_id,
                Student.tenant_id == tenant_id,
            )
        )
        student = student_result.scalar_one_or_none()
        if student:
            if log.channel in CHANNELS:
                # Descadastro recebido de um provedor afeta apenas aquele canal.
                # Ex.: STOP por SMS não bloqueia e-mail nem WhatsApp.
                apply_preference_changes(
                    session,
                    tenant_id=tenant_id,
                    student=student,
                    channels={log.channel: False},
                    source="provider_webhook",
                    method="unsubscribe_event",
                    location=f"provider:{event.provider}",
                    source_reference=event.event_id,
                )
            else:
                # Se não houver um canal confiável no log, aplicar o bloqueio global
                # é a opção fail-closed para evitar novos contatos indesejados.
                apply_preference_changes(
                    session,
                    tenant_id=tenant_id,
                    student=student,
                    opt_out=True,
                    source="provider_webhook",
                    method="unsubscribe_event",
                    location=f"provider:{event.provider}",
                    source_reference=event.event_id,
                )
    engagement_type = {
        "delivered": "delivered",
        "read": "read",
        "failed": "failed",
        "rejected": "failed",
        "bounced": "failed",
        "invalid": "failed",
        "opted_out": "opted_out",
    }.get(event.status)
    if engagement_type and log.student_id:
        await record_engagement_event(
            session,
            tenant_id=tenant_id,
            student_id=log.student_id,
            event_key=f"delivery:{log.id}:{event.provider}:{event.event_id[:120]}",
            event_type=engagement_type,
            channel=log.channel,
            source="provider_webhook",
            provider=event.provider,
            intervention_log_id=log.id,
            occurred_at=event.occurred_at or datetime.now(timezone.utc),
            event_metadata={"delivery_status": event.status},
        )
    else:
        await session.commit()
    return {"updated": True, "log_id": log.id, "status": event.status}
