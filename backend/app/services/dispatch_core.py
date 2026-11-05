"""Durable dispatch core: tenant isolation, human approvals, recipient-level outbox.

No provider call is made by this module. All writes are explicit transactions.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


async def bind_tenant(db: AsyncSession, tenant_id: str) -> None:
    await db.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": tenant_id},
    )


async def audit(
    db: AsyncSession, *, tenant_id: str, event_type: str,
    campaign_id: str | None = None, item_id: str | None = None,
    details: dict[str, Any] | None = None, event_key: str | None = None,
) -> None:
    # Audit details must be metadata only: never store message bodies, contacts,
    # names, debtor balances or secret provider responses.
    await db.execute(
        text("""
            INSERT INTO dispatch_events
                (id, tenant_id, campaign_id, item_id, event_type, event_key, details)
            VALUES (:id, :tenant, :campaign, :item, :event, :key, CAST(:details AS jsonb))
            ON CONFLICT (tenant_id, event_key) DO NOTHING
        """),
        {
            "id": str(uuid4()), "tenant": tenant_id, "campaign": campaign_id,
            "item": item_id, "event": event_type,
            "key": event_key or str(uuid4()),
            "details": json.dumps(details or {}, ensure_ascii=False),
        },
    )


async def get_campaign(
    db: AsyncSession, *, tenant_id: str, campaign_id: str, lock: bool = False
) -> dict[str, Any] | None:
    await bind_tenant(db, tenant_id)
    suffix = " FOR UPDATE" if lock else ""
    result = await db.execute(
        text("""
            SELECT id, tenant_id, name, purpose, channel, delivery_mode, request_key, template_ref, template_body,
                   status, authorization_ref, created_by, approved_by, approved_at,
                   scheduled_for, timezone, start_hour, end_hour,
                   per_minute_limit, daily_contact_limit, paused_reason,
                   created_at, updated_at
            FROM dispatch_campaigns
            WHERE tenant_id = :tenant AND id = :id
        """ + suffix),
        {"tenant": tenant_id, "id": campaign_id},
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def create_campaign(
    db: AsyncSession, *, tenant_id: str, created_by: str, name: str,
    purpose: str, channel: str, template_ref: str, template_body: str,
    per_minute_limit: int = 10, daily_contact_limit: int = 1,
    timezone_name: str = "America/Sao_Paulo",
    start_hour: int = 9, end_hour: int = 18, delivery_mode: str = "targeted",
) -> dict[str, Any]:
    if purpose not in {"retention", "academic", "service", "collections"} or channel not in {"email", "sms", "whatsapp"}:
        raise ValueError("Finalidade ou canal inválido.")
    if purpose == "collections" and channel == "whatsapp":
        raise ValueError("Cobrança via WhatsApp não está habilitada pelas políticas de canal.")
    if delivery_mode not in {"targeted", "bulk"}:
        raise ValueError("Intervenção individual deve usar /dispatch/interventions.")
    if not template_ref.strip() or not template_body.strip():
        raise ValueError("O modelo de mensagem é obrigatório.")
    if len(template_body) > 2000 or len(template_ref) > 160:
        raise ValueError("Modelo de mensagem excede os limites.")
    if per_minute_limit < 1 or per_minute_limit > 120:
        raise ValueError("Limite por minuto inválido.")
    if daily_contact_limit < 1 or daily_contact_limit > 3:
        raise ValueError("Limite diário inválido.")
    if start_hour < 8 or end_hour > 20 or end_hour <= start_hour:
        raise ValueError("Janela de contato inválida.")
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    try:
        ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("Fuso horário desconhecido.") from exc

    await bind_tenant(db, tenant_id)
    id_ = str(uuid4())
    await db.execute(text("""
        INSERT INTO dispatch_campaigns (
            id, tenant_id, name, purpose, channel, delivery_mode, template_ref, template_body,
            created_by, per_minute_limit, daily_contact_limit, timezone, start_hour, end_hour
        ) VALUES (
            :id, :tenant, :name, :purpose, :channel, :mode, :template_ref, :body,
            :actor, :rpm, :daily, :timezone, :start, :end
        )
    """), {
        "id": id_, "tenant": tenant_id, "name": name.strip(), "purpose": purpose,
        "channel": channel, "mode": delivery_mode,
        "template_ref": template_ref.strip(), "body": template_body,
        "actor": created_by, "rpm": per_minute_limit, "daily": daily_contact_limit,
        "timezone": timezone_name, "start": start_hour, "end": end_hour,
    })
    await audit(db, tenant_id=tenant_id, campaign_id=id_,
                event_type="campaign.created", details={"actor": created_by})
    await db.commit()
    return (await get_campaign(db, tenant_id=tenant_id, campaign_id=id_)) or {}


async def enqueue_recipients(
    db: AsyncSession, *, tenant_id: str, campaign_id: str,
    targets: list[dict[str, Any]], actor: str,
) -> dict[str, int]:
    if not targets or len(targets) > 1000:
        raise ValueError("Informe entre 1 e 1000 destinatários por lote.")
    campaign = await get_campaign(db, tenant_id=tenant_id, campaign_id=campaign_id, lock=True)
    if campaign is None:
        raise LookupError("Campanha não encontrada.")
    if campaign["status"] != "draft":
        raise ValueError("Audiência só pode ser alterada em uma campanha rascunho.")
    if campaign["delivery_mode"] == "individual":
        raise ValueError("A audiência individual é imutável e criada na intervenção.")
    created = skipped = 0
    for item in targets:
        kind = item.get("subject_type")
        ref = (item.get("subject_ref") or "").strip()
        obligation = (item.get("obligation_ref") or "").strip() or None
        consent = (item.get("consent_ref") or "").strip()
        if kind not in {"student", "external"} or not ref or len(ref) > 160:
            raise ValueError("Destinatário inválido.")
        if not consent or len(consent) > 200:
            raise ValueError("Cada destinatário exige referência verificável de autorização.")
        from app.services.dispatch_interventions import verified_authorization
        allowed = await verified_authorization(
            db, tenant_id=tenant_id, subject_type=kind, subject_ref=ref,
            channel=campaign["channel"], purpose=campaign["purpose"],
            evidence_ref=consent,
        )
        if not allowed:
            raise ValueError("Referência de contato não verificada, revogada ou expirada.")
        suppressed = (await db.execute(text("""
            SELECT 1 FROM dispatch_suppressions
            WHERE tenant_id=:tenant AND subject_type=:kind AND subject_ref=:ref
              AND channel IN ('all', :channel)
        """), {"tenant": tenant_id, "kind": kind, "ref": ref,
                 "channel": campaign["channel"]})).first()
        if suppressed:
            raise ValueError("Destinatário com bloqueio de contato registrado.")
        if campaign["purpose"] == "collections" and not obligation:
            raise ValueError("Cobrança exige referência de obrigação para revalidação.")
        if kind == "student":
            exists = (await db.execute(
                text("SELECT 1 FROM students WHERE tenant_id=:tenant AND id::text=:id AND is_active IS TRUE"),
                {"tenant": tenant_id, "id": ref},
            )).first()
            if not exists:
                raise ValueError("Aluno não encontrado neste workspace.")
        else:
            # External audiences require an encrypted, pre-verified contact.
            contact = (await db.execute(text("""
                SELECT 1 FROM dispatch_external_contacts WHERE tenant_id=:tenant
                AND subject_ref=:ref AND channel=:channel
                AND consent_ref=:consent AND opt_out IS FALSE
            """), {"tenant": tenant_id, "ref": ref, "channel": campaign["channel"],
                     "consent": consent})).first()
            if not contact:
                raise ValueError("Contato externo não verificado ou desautorizado.")
        if obligation:
            exists = (await db.execute(text("""
                SELECT 1 FROM dispatch_obligations
                WHERE tenant_id=:tenant AND external_ref=:ref
                AND subject_type=:kind AND subject_ref=:subject AND status='open'
            """), {"tenant": tenant_id, "ref": obligation, "kind": kind, "subject": ref})).first()
            if not exists:
                raise ValueError("Obrigação inexistente ou não elegível no workspace.")
        created_id = str(uuid4())
        result = await db.execute(text("""
            INSERT INTO dispatch_items
                (id, tenant_id, campaign_id, subject_type, subject_ref,
                 obligation_ref, consent_ref, channel)
            VALUES (:id, :tenant, :campaign, :kind, :ref, :obligation, :consent, :channel)
            ON CONFLICT DO NOTHING RETURNING id
        """), {
            "id": created_id, "tenant": tenant_id, "campaign": campaign_id,
            "kind": kind, "ref": ref, "obligation": obligation,
            "consent": consent, "channel": campaign["channel"],
        })
        if result.scalar_one_or_none():
            created += 1
        else:
            skipped += 1
    await audit(db, tenant_id=tenant_id, campaign_id=campaign_id,
                event_type="audience.staged",
                details={"actor": actor, "created": created, "duplicates": skipped})
    await db.commit()
    return {"created": created, "duplicates": skipped}


ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"approved", "cancelled"},
    "approved": {"scheduled", "running", "cancelled"},
    "scheduled": {"running", "paused", "cancelled"},
    "running": {"paused", "completed", "cancelled"},
    "paused": {"running", "cancelled"},
    "completed": set(),
    "cancelled": set(),
}


async def transition_campaign(
    db: AsyncSession, *, tenant_id: str, campaign_id: str, actor: str,
    target: str, authorization_ref: str | None = None,
    scheduled_for: datetime | None = None,
) -> dict[str, Any]:
    campaign = await get_campaign(db, tenant_id=tenant_id, campaign_id=campaign_id, lock=True)
    if campaign is None:
        raise LookupError("Campanha não encontrada.")
    current = campaign["status"]
    if target not in ALLOWED_TRANSITIONS.get(current, set()):
        raise ValueError(f"Transição não permitida: {current} → {target}")
    if target == "approved":
        if not actor or actor == campaign["created_by"]:
            raise ValueError("Aprovação exige outro usuário autenticado (quatro olhos).")
        if not authorization_ref or len(authorization_ref.strip()) < 8:
            raise ValueError("Aprovação exige evidência institucional de comunicação.")
        total = (await db.execute(text("""
            SELECT count(*) FROM dispatch_items WHERE tenant_id=:tenant AND campaign_id=:id
        """), {"tenant": tenant_id, "id": campaign_id})).scalar_one()
        if total == 0:
            raise ValueError("Adicione uma audiência antes de aprovar.")
    if target == "running":
        if not campaign["approved_at"] or not campaign["authorization_ref"]:
            raise ValueError("Campanha sem aprovação e autorização verificadas.")
    if target == "scheduled" and (scheduled_for is None or scheduled_for <= now_utc()):
        raise ValueError("O agendamento deve ser futuro.")
    await db.execute(text("""
        UPDATE dispatch_campaigns
        SET status=:status, updated_at=now(),
            approved_at=CASE WHEN :status='approved' THEN now() ELSE approved_at END,
            approved_by=CASE WHEN :status='approved' THEN :actor ELSE approved_by END,
            authorization_ref=CASE WHEN :status='approved' THEN :authorization ELSE authorization_ref END,
            scheduled_for=CASE WHEN :status='scheduled' THEN :schedule ELSE scheduled_for END,
            paused_reason=CASE WHEN :status='paused' THEN 'manual' ELSE NULL END
        WHERE tenant_id=:tenant AND id=:id
    """), {
        "status": target, "actor": actor, "authorization": authorization_ref,
        "schedule": scheduled_for, "tenant": tenant_id, "id": campaign_id,
    })
    if target == "cancelled":
        await db.execute(text("""
            UPDATE dispatch_items SET status='cancelled', lease_until=NULL, lease_token=NULL,
                updated_at=now() WHERE tenant_id=:tenant AND campaign_id=:id
                AND status IN ('queued','retry_wait','leased')
        """), {"tenant": tenant_id, "id": campaign_id})
    await audit(db, tenant_id=tenant_id, campaign_id=campaign_id,
                event_type=f"campaign.{target}", details={"actor": actor})
    await db.commit()
    return (await get_campaign(db, tenant_id=tenant_id, campaign_id=campaign_id)) or {}


async def list_campaigns(db: AsyncSession, *, tenant_id: str, limit: int = 50) -> list[dict[str, Any]]:
    await bind_tenant(db, tenant_id)
    rows = await db.execute(text("""
        SELECT c.id,c.name,c.purpose,c.channel,c.delivery_mode,c.status,c.created_at,c.scheduled_for,
               c.paused_reason, c.template_ref,
               count(i.id) AS total,
               count(i.id) FILTER (WHERE i.status IN ('queued','retry_wait','leased','sending')) AS pending,
               count(i.id) FILTER (WHERE i.status IN ('sent','delivered','read','replied')) AS accepted,
               count(i.id) FILTER (WHERE i.status='simulated') AS simulated,
               count(i.id) FILTER (WHERE i.status IN ('blocked','failed','unknown')) AS problems,
               count(i.id) FILTER (WHERE i.status='replied') AS replied
        FROM dispatch_campaigns c LEFT JOIN dispatch_items i
          ON i.campaign_id=c.id AND i.tenant_id=c.tenant_id
        WHERE c.tenant_id=:tenant
        GROUP BY c.id ORDER BY c.created_at DESC LIMIT :limit
    """), {"tenant": tenant_id, "limit": limit})
    return [dict(row) for row in rows.mappings().all()]


async def campaign_items(
    db: AsyncSession, *, tenant_id: str, campaign_id: str, limit: int = 100,
) -> list[dict[str, Any]]:
    await bind_tenant(db, tenant_id)
    rows = await db.execute(text("""
        SELECT id, subject_type, subject_ref, obligation_ref, channel,
               status, attempt, scheduled_for, updated_at, last_error
        FROM dispatch_items WHERE tenant_id=:tenant AND campaign_id=:campaign
        ORDER BY created_at DESC LIMIT :limit
    """), {"tenant": tenant_id, "campaign": campaign_id, "limit": limit})
    return [dict(row) for row in rows.mappings().all()]


def classify_reply(message: str) -> tuple[str, str]:
    """Conservative intent suggestion. Never negotiates or sends automatically."""
    plain = " ".join(message.casefold().split())[:1000]
    if any(token in plain for token in ("número errado", "numero errado", "não sou", "nao sou")):
        return "wrong_recipient", "suppress_and_review"
    # Explicit refusal wins even when the same message also disputes a charge.
    if any(token in plain for token in ("pare", "não envie", "nao envie", "sair", "stop")):
        return "opt_out", "suppress_contact"
    if any(token in plain for token in ("não reconheço", "nao reconheco", "contesto")):
        return "dispute", "human_review"
    if any(token in plain for token in ("já paguei", "ja paguei", "comprovante")):
        return "claims_paid", "reconcile_payment"
    if any(token in plain for token in ("negociar", "parcelar", "acordo")):
        return "negotiate", "human_negotiation"
    return "other", "human_review"


def dedupe_digest(tenant_id: str, provider: str, event_id: str) -> str:
    return hashlib.sha256(f"{tenant_id}:{provider}:{event_id}".encode()).hexdigest()
