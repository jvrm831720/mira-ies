"""Delivery policy and adapter. Collection WhatsApp is refused; live is opt-in twice."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parseaddr
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings


@dataclass(frozen=True)
class Eligibility:
    allowed: bool
    reason: str
    destination: str | None = None
    display_name: str = ""


def channel_allowed(purpose: str, channel: str) -> bool:
    # Under the current WhatsApp Business policy, debt collection is not enabled.
    if purpose == "collections" and channel == "whatsapp":
        return False
    return channel in {"email", "sms", "whatsapp"}


def inside_contact_window(
    instant: datetime, timezone_name: str, start_hour: int, end_hour: int,
) -> bool:
    local = instant.astimezone(ZoneInfo(timezone_name))
    return local.weekday() < 5 and start_hour <= local.hour < end_hour


def live_enabled(tenant_id: str, channel: str) -> bool:
    settings = get_settings()
    tenants = {x.strip() for x in settings.dispatch_live_tenants.split(",") if x.strip()}
    channels = {x.strip() for x in settings.dispatch_live_channels.split(",") if x.strip()}
    return (
        settings.dispatch_live_enabled
        and tenant_id in tenants
        and channel in channels
        and channel in {"email", "sms"}
    )


def encrypt_destination(value: str) -> str:
    key = get_settings().dispatch_contact_encryption_key
    if not key:
        raise ValueError("DISPATCH_CONTACT_ENCRYPTION_KEY não configurada.")
    try:
        return Fernet(key.encode()).encrypt(value.encode()).decode()
    except (ValueError, TypeError) as exc:
        raise ValueError("Chave de criptografia de contatos inválida.") from exc


def decrypt_destination(ciphertext: str) -> str | None:
    key = get_settings().dispatch_contact_encryption_key
    if not key:
        return None
    try:
        return Fernet(key.encode()).decrypt(ciphertext.encode()).decode()
    except (ValueError, TypeError, InvalidToken):
        return None


def normalize_destination(channel: str, value: str) -> str | None:
    raw = value.strip()
    if channel == "email":
        _, address = parseaddr(raw)
        if address != raw or "@" not in address or "." not in address.split("@")[-1] or len(address) > 254:
            return None
        return address.lower()
    if channel in {"sms", "whatsapp"}:
        from app.agents.channels.whatsapp import normalize_phone_br
        return normalize_phone_br(raw)
    return None


async def eligibility(
    db: AsyncSession, *, tenant_id: str, campaign: dict[str, Any],
    item: dict[str, Any], instant: datetime | None = None,
) -> Eligibility:
    now = instant or datetime.now(timezone.utc)
    if campaign["status"] != "running" or not campaign["approved_at"] or not campaign["authorization_ref"]:
        return Eligibility(False, "campaign_not_authorized")
    if not channel_allowed(campaign["purpose"], campaign["channel"]):
        return Eligibility(False, "channel_policy")
    if campaign["purpose"] == "collections" and campaign["channel"] == "whatsapp":
        return Eligibility(False, "collection_whatsapp_blocked")
    if not inside_contact_window(now, campaign["timezone"], campaign["start_hour"], campaign["end_hour"]):
        return Eligibility(False, "outside_contact_window")
    if not item.get("consent_ref"):
        return Eligibility(False, "missing_contact_basis")
    suppressed = (await db.execute(text("""
        SELECT 1 FROM dispatch_suppressions
        WHERE tenant_id=:tenant AND subject_type=:kind AND subject_ref=:ref
          AND channel IN ('all', :channel)
    """), {"tenant": tenant_id, "kind": item["subject_type"],
           "ref": item["subject_ref"], "channel": campaign["channel"]})).first()
    if suppressed:
        return Eligibility(False, "recipient_suppressed")
    if campaign["purpose"] == "collections":
        obligation = (await db.execute(text("""
            SELECT status, balance, verified_at FROM dispatch_obligations
            WHERE tenant_id=:tenant AND external_ref=:ref
            AND subject_type=:kind AND subject_ref=:subject
        """), {
            "tenant": tenant_id, "ref": item.get("obligation_ref"),
            "kind": item["subject_type"], "subject": item["subject_ref"],
        })).mappings().first()
        if (
            obligation is None or obligation["status"] != "open"
            or obligation["balance"] is None or obligation["balance"] <= 0
            or obligation["verified_at"] < now - timedelta(minutes=15)
        ):
            return Eligibility(False, "obligation_not_fresh_or_open")

    # Daily cross-campaign cap, including messages already in flight.
    concurrent = (await db.execute(text("""
        SELECT count(*) FROM dispatch_items
        WHERE tenant_id=:tenant AND subject_type=:kind AND subject_ref=:ref
          AND channel=:channel AND id<>:id AND (
          (status IN ('sent','delivered','read','replied') AND sent_at >= :cutoff)
          OR (status='sending' AND updated_at >= :cutoff)
        )
    """), {
        "tenant": tenant_id, "kind": item["subject_type"],
        "ref": item["subject_ref"], "channel": campaign["channel"],
        "id": item["id"], "cutoff": now - timedelta(hours=24),
    })).scalar_one()
    if concurrent >= campaign["daily_contact_limit"]:
        return Eligibility(False, "daily_contact_cap")

    if item["subject_type"] == "student":
        try:
            student_id = str(UUID(item["subject_ref"]))
        except ValueError:
            return Eligibility(False, "invalid_student_id")
        student = (await db.execute(text("""
            SELECT nome, telefone, email, communication_opt_out,
                   communication_preferences, is_active
            FROM students WHERE tenant_id=:tenant AND id=:id
        """), {"tenant": tenant_id, "id": student_id})).mappings().first()
        if student is None or not student["is_active"] or student["communication_opt_out"]:
            return Eligibility(False, "student_inactive_or_opt_out")
        prefs = student["communication_preferences"] or {}
        # Missing preference is NOT consent; fail closed, even if old code defaults to True.
        if prefs.get("channels", {}).get(campaign["channel"]) is not True:
            return Eligibility(False, "channel_consent_not_verified")
        if campaign["purpose"] == "retention" and prefs.get("topics", {}).get("retention") is not True:
            return Eligibility(False, "retention_purpose_not_verified")
        dest = student["email"] if campaign["channel"] == "email" else student["telefone"]
        normalized = normalize_destination(campaign["channel"], dest or "")
        if not normalized:
            return Eligibility(False, "invalid_destination")
        return Eligibility(True, "eligible", normalized, student["nome"] or "")

    contact = (await db.execute(text("""
        SELECT recipient_ciphertext, opt_out, verified_at, consent_ref
        FROM dispatch_external_contacts
        WHERE tenant_id=:tenant AND subject_ref=:ref AND channel=:channel
    """), {
        "tenant": tenant_id, "ref": item["subject_ref"], "channel": campaign["channel"],
    })).mappings().first()
    if (
        contact is None or contact["opt_out"] is not False
        or contact["consent_ref"] != item["consent_ref"]
        or contact["verified_at"] < now - timedelta(days=30)
    ):
        return Eligibility(False, "external_contact_not_verified")
    dest = decrypt_destination(contact["recipient_ciphertext"])
    normalized = normalize_destination(campaign["channel"], dest or "")
    if normalized is None:
        return Eligibility(False, "external_destination_unavailable")
    return Eligibility(True, "eligible", normalized, "")


async def allow_rate(
    db: AsyncSession, *, tenant_id: str, channel: str, campaign_id: str,
    campaign_rpm: int, instant: datetime | None = None,
) -> bool:
    """Atomic multi-bucket token reservation with transaction-scoped advisory locks."""
    now = instant or datetime.now(timezone.utc)
    buckets = [
        (f"tenant:{channel}", 30),
        (f"campaign:{campaign_id}:{channel}", min(30, campaign_rpm)),
    ]
    # Sorted keys make acquisition order stable for concurrent workers.
    buckets.sort(key=lambda row: row[0])
    for name, _ in buckets:
        await db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"dispatch:{tenant_id}:{name}"},
        )
    prepared: list[tuple[str, float]] = []
    for name, limit in buckets:
        row = (await db.execute(text("""
            SELECT tokens,updated_at FROM dispatch_rate_buckets
            WHERE tenant_id=:tenant AND bucket_key=:key FOR UPDATE
        """), {"tenant": tenant_id, "key": name})).mappings().first()
        if row is None:
            tokens = float(limit)
        else:
            elapsed = max(0.0, (now - row["updated_at"]).total_seconds())
            tokens = min(float(limit), float(row["tokens"]) + elapsed * limit / 60.0)
        if tokens < 1.0:
            return False
        prepared.append((name, tokens - 1.0))
    for name, tokens in prepared:
        await db.execute(text("""
            INSERT INTO dispatch_rate_buckets (tenant_id,bucket_key,tokens,updated_at)
            VALUES (:tenant,:key,:tokens,:now)
            ON CONFLICT (tenant_id,bucket_key)
            DO UPDATE SET tokens=EXCLUDED.tokens, updated_at=EXCLUDED.updated_at
        """), {"tenant": tenant_id, "key": name, "tokens": tokens, "now": now})
    return True


@dataclass(frozen=True)
class DeliveryResult:
    status: str
    provider: str
    provider_message_id: str | None = None
    error_code: str | None = None
    retryable: bool = False


async def send_authorized(
    *, tenant_id: str, campaign: dict[str, Any],
    item: dict[str, Any], destination: str, display_name: str,
) -> DeliveryResult:
    """Only email/SMS can be live, and only with both server-side opt-ins."""
    if not live_enabled(tenant_id, campaign["channel"]):
        return DeliveryResult("simulated", "simulation")
    body = campaign["template_body"].replace("{nome}", display_name[:150])
    idempotency_key = f"mira-dispatch:{item['id']}"
    if campaign["channel"] == "email":
        from app.agents.providers.resend_provider import send_email_resend
        result = await send_email_resend(
            to=destination, subject=campaign["template_ref"][:150],
            body=body, idempotency_key=idempotency_key,
        )
        provider = "resend"
    elif campaign["channel"] == "sms":
        from app.agents.providers.twilio_provider import send_sms_twilio
        result = await send_sms_twilio(
            to=destination, message=body, idempotency_key=idempotency_key,
        )
        provider = "twilio"
    else:
        return DeliveryResult("blocked", "policy", error_code="channel_not_authorized")

    if result.ok:
        return DeliveryResult("sent", provider, result.external_id)
    if getattr(result, "outcome", None) == "unknown" or getattr(result, "ambiguous", False):
        return DeliveryResult("unknown", provider, error_code="provider_uncertain")
    error = (result.error or "").lower()
    retryable = any(token in error for token in ("429", "500", "502", "503", "504"))
    return DeliveryResult("failed", provider, error_code="provider_failed", retryable=retryable)
