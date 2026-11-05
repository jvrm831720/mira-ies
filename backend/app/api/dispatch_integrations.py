"""Verified connector ingress + signed delivery/reply webhooks + payment reconciliation.

Provider events are accepted only from an internal gateway that validates its
upstream provider and signs the normalized JSON body. No arbitrary public
delivery status endpoint exists.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthContext, require_permission
from app.core.config import get_settings
from app.db.session import AsyncSessionLocal, get_db
from app.models.student import Student
from app.services.consent import apply_preference_changes
from app.services.dispatch_core import audit, bind_tenant, classify_reply
from app.services.dispatch_delivery import encrypt_destination, normalize_destination

router = APIRouter(prefix="/dispatch", tags=["Dispatch Integration"])


def _require_connector(auth: AuthContext) -> None:
    if auth.user_id is not None or auth.role is not None:
        raise HTTPException(status_code=403, detail="Somente integração autenticada pode atualizar evidências.")


class ObligationSync(BaseModel):
    external_ref: str = Field(min_length=1, max_length=160)
    subject_type: Literal["student", "external"]
    subject_ref: str = Field(min_length=1, max_length=160)
    status: Literal["open", "paid", "disputed", "agreement", "cancelled", "unknown"]
    balance: Decimal | None = Field(default=None, ge=0)
    source: str = Field(min_length=3, max_length=80)
    evidence_ref: str = Field(min_length=8, max_length=200)


class ContactSync(BaseModel):
    subject_ref: str = Field(min_length=1, max_length=160)
    channel: Literal["email", "sms"]
    recipient: str = Field(min_length=5, max_length=255)
    consent_ref: str = Field(min_length=8, max_length=200)
    opt_out: bool = True


class PaymentSync(BaseModel):
    obligation_ref: str = Field(min_length=1, max_length=160)
    source: str = Field(min_length=3, max_length=80)
    source_event_id: str = Field(min_length=6, max_length=160)
    amount_paid: Decimal = Field(ge=0, le=999999999999)
    evidence_ref: str = Field(min_length=8, max_length=200)
    new_status: Literal["open", "paid", "agreement", "disputed"]
    balance: Decimal = Field(ge=0)


@router.post("/integrations/obligations")
async def upsert_obligation(
    body: ObligationSync,
    auth: AuthContext = Depends(require_permission("data.import", allow_service_key=True)),
    db: AsyncSession = Depends(get_db),
):
    _require_connector(auth)
    await bind_tenant(db, auth.tenant_id)
    if body.status == "open" and (body.balance is None or body.balance <= 0):
        raise HTTPException(status_code=422, detail="Saldo positivo é obrigatório para obrigação aberta.")
    await db.execute(text("""
        INSERT INTO dispatch_obligations (
            id, tenant_id, external_ref, subject_type, subject_ref, status,
            balance, source, evidence_ref, verified_at
        ) VALUES (:id, :tenant, :ref, :kind, :subject, :status, :balance, :source, :evidence, now())
        ON CONFLICT (tenant_id,external_ref) DO UPDATE SET
            status=EXCLUDED.status, balance=EXCLUDED.balance,
            source=EXCLUDED.source, evidence_ref=EXCLUDED.evidence_ref,
            verified_at=now(), updated_at=now()
        WHERE dispatch_obligations.subject_type=EXCLUDED.subject_type
          AND dispatch_obligations.subject_ref=EXCLUDED.subject_ref
    """), {
        "id": str(uuid4()), "tenant": auth.tenant_id,
        "ref": body.external_ref, "kind": body.subject_type,
        "subject": body.subject_ref, "status": body.status,
        "balance": body.balance, "source": body.source,
        "evidence": body.evidence_ref,
    })
    if body.status != "open":
        await db.execute(text("""
            UPDATE dispatch_items SET status='blocked', last_error='obligation_no_longer_open',
                updated_at=now() WHERE tenant_id=:tenant AND obligation_ref=:ref
              AND status IN ('queued','retry_wait','leased')
        """), {"tenant": auth.tenant_id, "ref": body.external_ref})
    await audit(db, tenant_id=auth.tenant_id, event_type="obligation.synced",
                details={"ref_hash": hashlib.sha256(body.external_ref.encode()).hexdigest()[:12],
                         "status": body.status, "source": body.source})
    await db.commit()
    return {"accepted": True, "status": body.status}


@router.post("/integrations/contacts")
async def upsert_external_contact(
    body: ContactSync,
    auth: AuthContext = Depends(require_permission("data.import", allow_service_key=True)),
    db: AsyncSession = Depends(get_db),
):
    _require_connector(auth)
    dest = normalize_destination(body.channel, body.recipient)
    if not dest:
        raise HTTPException(status_code=422, detail="Contato inválido.")
    try:
        ciphertext = encrypt_destination(dest)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    await bind_tenant(db, auth.tenant_id)
    await db.execute(text("""
        INSERT INTO dispatch_external_contacts
            (id, tenant_id, subject_ref, channel, recipient_ciphertext,
             consent_ref, opt_out, verified_at)
        VALUES (:id,:tenant,:subject,:channel,:ciphertext,:consent,:opt_out,now())
        ON CONFLICT (tenant_id,subject_ref,channel) DO UPDATE SET
          recipient_ciphertext=EXCLUDED.recipient_ciphertext,
          consent_ref=EXCLUDED.consent_ref, opt_out=EXCLUDED.opt_out,
          verified_at=now()
    """), {
        "id": str(uuid4()), "tenant": auth.tenant_id,
        "subject": body.subject_ref, "channel": body.channel,
        "ciphertext": ciphertext, "consent": body.consent_ref,
        "opt_out": body.opt_out,
    })
    await audit(db, tenant_id=auth.tenant_id,
                event_type="contact.verified", details={"channel": body.channel})
    await db.commit()
    return {"accepted": True, "channel": body.channel}


@router.post("/integrations/payments")
async def reconcile_payment(
    body: PaymentSync,
    auth: AuthContext = Depends(require_permission("data.import", allow_service_key=True)),
    db: AsyncSession = Depends(get_db),
):
    """Signed connector-derived payment fact; never create a settlement from a reply."""
    _require_connector(auth)
    if body.new_status == "paid" and body.balance != 0:
        raise HTTPException(status_code=422, detail="Quitação exige saldo zero.")
    await bind_tenant(db, auth.tenant_id)
    current = (await db.execute(text("""
        SELECT source FROM dispatch_obligations WHERE tenant_id=:tenant AND external_ref=:ref
        FOR UPDATE
    """), {"tenant": auth.tenant_id, "ref": body.obligation_ref})).mappings().first()
    if current is None or current["source"] != body.source:
        raise HTTPException(status_code=404, detail="Obrigação inexistente ou fonte não corresponde.")
    prior = (await db.execute(text("""
        SELECT obligation_ref, amount_paid, evidence_ref FROM dispatch_payment_events
        WHERE tenant_id=:tenant AND source=:source AND source_event_id=:event
    """), {"tenant": auth.tenant_id, "source": body.source, "event": body.source_event_id})).mappings().first()
    if prior:
        if (prior["obligation_ref"] != body.obligation_ref
                or prior["amount_paid"] != body.amount_paid
                or prior["evidence_ref"] != body.evidence_ref):
            raise HTTPException(status_code=409, detail="Evento de pagamento reutilizado com conteúdo diferente.")
        return {"replayed": True, "accepted": True}
    await db.execute(text("""
        INSERT INTO dispatch_payment_events
            (id, tenant_id, obligation_ref, source, source_event_id,
             amount_paid, evidence_ref, paid_at)
        VALUES (:id,:tenant,:obligation,:source,:event,:amount,:evidence,now())
    """), {
        "id": str(uuid4()), "tenant": auth.tenant_id, "obligation": body.obligation_ref,
        "source": body.source, "event": body.source_event_id,
        "amount": body.amount_paid, "evidence": body.evidence_ref,
    })
    await db.execute(text("""
        UPDATE dispatch_obligations
        SET status=:status, balance=:balance, verified_at=now(), updated_at=now(),
            evidence_ref=:evidence
        WHERE tenant_id=:tenant AND external_ref=:obligation
    """), {
        "status": body.new_status, "balance": body.balance,
        "evidence": body.evidence_ref, "tenant": auth.tenant_id,
        "obligation": body.obligation_ref,
    })
    if body.new_status != "open":
        await db.execute(text("""
            UPDATE dispatch_items SET status='blocked',last_error='payment_or_agreement',
                 updated_at=now()
            WHERE tenant_id=:tenant AND obligation_ref=:obligation
              AND status IN ('queued','retry_wait','leased')
        """), {"tenant": auth.tenant_id, "obligation": body.obligation_ref})
    await audit(db, tenant_id=auth.tenant_id,
                event_type="payment.reconciled", details={
                    "source": body.source, "status": body.new_status,
                    "event_hash": hashlib.sha256(body.source_event_id.encode()).hexdigest()[:12],
                })
    await db.commit()
    return {"accepted": True, "replayed": False, "status": body.new_status}


class VerifiedGatewayEvent(BaseModel):
    tenant_id: str
    provider_message_id: str = Field(min_length=1, max_length=200)
    external_event_id: str = Field(min_length=3, max_length=180)
    kind: Literal["delivered","read","reply","failed"]
    message: str | None = Field(default=None, max_length=1000)


def verify_gateway(raw: bytes, signature: str | None) -> bool:
    secret = get_settings().dispatch_webhook_secret
    if not secret or len(secret) < 32 or not signature:
        return False
    expected = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.post("/webhooks/{provider}")
async def verified_gateway_webhook(
    provider: Literal["resend", "twilio"],
    request: Request,
    signature: str | None = Header(None, alias="X-Mira-Dispatch-Signature"),
):
    """MIRA gateway must verify upstream provider signature before forwarding."""
    raw = await request.body()
    if len(raw) > 8192:
        raise HTTPException(status_code=413, detail="Evento muito grande.")
    if not get_settings().dispatch_webhook_secret:
        raise HTTPException(status_code=503, detail="Gateway de eventos indisponível.")
    if not verify_gateway(raw, signature):
        raise HTTPException(status_code=401, detail="Assinatura inválida.")
    try:
        event = VerifiedGatewayEvent.model_validate(json.loads(raw))
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=422, detail="Evento inválido.") from exc
    async with AsyncSessionLocal() as db:
        await bind_tenant(db, event.tenant_id)
        found = (await db.execute(text("""
            SELECT i.id,i.campaign_id,i.subject_type,i.subject_ref,i.obligation_ref,i.status
            FROM dispatch_items i WHERE i.tenant_id=:tenant
              AND i.provider=:provider AND i.provider_message_id=:message
            FOR UPDATE
        """), {
            "tenant": event.tenant_id, "provider": provider,
            "message": event.provider_message_id,
        })).mappings().first()
        if not found:
            return {"accepted": False, "reason": "unmatched"}
        item = dict(found)
        existing = (await db.execute(text("""
            SELECT id FROM dispatch_inbound
            WHERE tenant_id=:tenant AND provider=:provider AND external_event_id=:event
        """), {
            "tenant": event.tenant_id, "provider": provider,
            "event": event.external_event_id,
        })).scalar_one_or_none()
        if existing:
            return {"accepted": True, "replayed": True}
        intent, action = (classify_reply(event.message or "")
                          if event.kind == "reply" else (None, None))
        await db.execute(text("""
            INSERT INTO dispatch_inbound
                (id,tenant_id,item_id,provider,external_event_id,
                 event_kind,reply_intent,recommended_action)
            VALUES (:id,:tenant,:item,:provider,:event,:kind,:intent,:action)
        """), {
            "id": str(uuid4()), "tenant": event.tenant_id, "item": item["id"],
            "provider": provider, "event": event.external_event_id,
            "kind": event.kind, "intent": intent, "action": action,
        })
        target = {
            "delivered": "delivered", "read": "read",
            "reply": "replied", "failed": "failed",
        }[event.kind]
        if item["status"] in {"sent","delivered","read","replied"}:
            if not (item["status"] == "replied" and target in {"delivered","read"}):
                await db.execute(text("""
                    UPDATE dispatch_items SET status=:status,updated_at=now()
                    WHERE id=:id AND tenant_id=:tenant
                """), {"status": target, "id": item["id"], "tenant": event.tenant_id})
        if intent in {"opt_out", "wrong_recipient"}:
            if item["subject_type"] == "external":
                await db.execute(text("""
                    UPDATE dispatch_external_contacts SET opt_out=TRUE
                    WHERE tenant_id=:tenant AND subject_ref=:ref
                """), {"tenant": event.tenant_id, "ref": item["subject_ref"]})
            elif item["subject_type"] == "student":
                student = (await db.execute(select(Student).where(
                    Student.tenant_id == event.tenant_id,
                    Student.id == item["subject_ref"],
                ))).scalar_one_or_none()
                if student:
                    apply_preference_changes(
                        db, tenant_id=event.tenant_id, student=student,
                        opt_out=True, source="dispatch_gateway", method="verified_webhook",
                        location="/api/v1/dispatch/webhooks",
                        source_reference=event.external_event_id,
                    )
            await db.execute(text("""
                UPDATE dispatch_items SET status='blocked',last_error='recipient_suppressed',
                    updated_at=now() WHERE tenant_id=:tenant AND subject_type=:kind
                    AND subject_ref=:ref AND status IN ('queued','retry_wait','leased')
            """), {"tenant": event.tenant_id,
                   "kind": item["subject_type"], "ref": item["subject_ref"]})
        elif intent in {"claims_paid", "dispute"} and item["obligation_ref"]:
            await db.execute(text("""
                UPDATE dispatch_items SET status='blocked', last_error='needs_financial_review',
                    updated_at=now()
                WHERE tenant_id=:tenant AND obligation_ref=:obligation
                  AND status IN ('queued','retry_wait','leased')
            """), {"tenant": event.tenant_id, "obligation": item["obligation_ref"]})
        await audit(db, tenant_id=event.tenant_id,
                    campaign_id=str(item["campaign_id"]), item_id=str(item["id"]),
                    event_type=f"gateway.{event.kind}",
                    event_key=f"gateway:{provider}:{event.external_event_id}",
                    details={"intent": intent, "action": action, "provider": provider})
        await db.commit()
        return {"accepted": True, "replayed": False, "intent": intent}


@router.get("/recovery/summary")
async def financial_results(
    auth: AuthContext = Depends(require_permission("audit.view")),
    db: AsyncSession = Depends(get_db),
):
    await bind_tenant(db, auth.tenant_id)
    paid = (await db.execute(text("""
        SELECT count(*) AS transactions,coalesce(sum(amount_paid),0) AS received_brl
        FROM dispatch_payment_events WHERE tenant_id=:tenant
    """), {"tenant": auth.tenant_id})).mappings().one()
    obligations = (await db.execute(text("""
        SELECT status,count(*) AS count FROM dispatch_obligations
        WHERE tenant_id=:tenant GROUP BY status
    """), {"tenant": auth.tenant_id})).mappings().all()
    return {
        "payments": dict(paid),
        "obligations": {row["status"]: row["count"] for row in obligations},
        "note": "Recebimento conciliado não prova atribuição causal ao disparo.",
    }
