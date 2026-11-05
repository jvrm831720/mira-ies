"""Verified connector ingress + signed delivery/reply webhooks + payment reconciliation.

Provider events are accepted only from an internal gateway that validates its
upstream provider and signs the normalized JSON body. No arbitrary public
delivery status endpoint exists.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from decimal import Decimal
from datetime import datetime, timezone, timedelta
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
from app.services.dispatch_ingress_security import verify as verify_source

router = APIRouter(prefix="/dispatch", tags=["Dispatch Integration"])


def _require_connector(auth: AuthContext) -> None:
    # get_current_tenant currently labels verified API keys with role="admin".
    # A service key has no human user/session; never use role to distinguish it.
    if auth.user_id is not None or auth.session_id is not None:
        raise HTTPException(status_code=403, detail="Somente integração autenticada pode atualizar evidências.")


class ObligationSync(BaseModel):
    external_ref: str = Field(min_length=1, max_length=160)
    subject_type: Literal["student", "external"]
    subject_ref: str = Field(min_length=1, max_length=160)
    status: Literal["open", "paid", "disputed", "agreement", "cancelled", "unknown"]
    balance: Decimal | None = Field(default=None, ge=0)
    source: str = Field(min_length=3, max_length=80)
    evidence_ref: str = Field(min_length=8, max_length=200)
    source_version: int = Field(ge=1)
    observed_at: datetime


class ContactSync(BaseModel):
    source: str = Field(min_length=3,max_length=80)
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
    source_version: int = Field(ge=1)
    observed_at: datetime


def _verified_observation(observed: datetime) -> None:
    if observed.tzinfo is None or observed.utcoffset() is None:
        raise HTTPException(status_code=422,detail="A verificação exige timestamp com fuso.")
    now=datetime.now(timezone.utc)
    if observed > now+timedelta(minutes=5) or observed < now-timedelta(days=30):
        raise HTTPException(status_code=422,detail="Observação financeira fora da janela confiável.")


@router.post("/integrations/obligations")
async def upsert_obligation(
    body: ObligationSync,
    request: Request,
    auth: AuthContext = Depends(require_permission("data.import", allow_service_key=True)),
    db: AsyncSession = Depends(get_db),
):
    """One authoritative source per debt; only higher source versions can mutate it."""
    _require_connector(auth)
    await verify_source(
        db, tenant_id=auth.tenant_id,source=body.source,
        scope="financial",request=request,
    )
    _verified_observation(body.observed_at)
    if body.status=="open" and (body.balance is None or body.balance<=0):
        raise HTTPException(status_code=422,detail="Obrigação aberta precisa de saldo positivo.")
    await bind_tenant(db,auth.tenant_id)
    existing=(await db.execute(text("""
        SELECT subject_type,subject_ref,source,source_version,status,balance,
               evidence_ref,verified_at
        FROM dispatch_obligations
        WHERE tenant_id=:tenant AND external_ref=:ref FOR UPDATE
    """), {"tenant":auth.tenant_id,"ref":body.external_ref})).mappings().first()
    if existing:
        if (existing["subject_type"]!=body.subject_type
             or existing["subject_ref"]!=body.subject_ref
             or existing["source"]!=body.source):
            raise HTTPException(status_code=409,detail="Dívida vinculada a outra fonte ou destinatário.")
        if body.source_version==existing["source_version"]:
            if (existing["status"]==body.status and existing["balance"]==body.balance
                  and existing["evidence_ref"]==body.evidence_ref
                  and existing["verified_at"]==body.observed_at):
                await db.commit()  # reserve signed request nonce
                return {"accepted":True,"replayed":True,"status":body.status}
            raise HTTPException(status_code=409,detail="Versão da origem duplicada com conteúdo divergente.")
        if body.source_version<existing["source_version"]:
            raise HTTPException(status_code=409,detail="Observação financeira anterior à última versão.")
        if existing["status"] in {"paid","disputed","agreement","cancelled"} and body.status=="open":
            raise HTTPException(status_code=409,detail="Reabertura de dívida terminal exige nova referência e revisão.")
    await db.execute(text("""
        INSERT INTO dispatch_obligations
            (id,tenant_id,external_ref,subject_type,subject_ref,status,balance,
             source,evidence_ref,source_version,verified_at)
        VALUES (:id,:tenant,:ref,:kind,:subject,:status,:balance,
                :source,:evidence,:version,:observed)
        ON CONFLICT (tenant_id,external_ref) DO UPDATE SET
            status=EXCLUDED.status,balance=EXCLUDED.balance,source=EXCLUDED.source,
            evidence_ref=EXCLUDED.evidence_ref,source_version=EXCLUDED.source_version,
            verified_at=EXCLUDED.verified_at,updated_at=now()
        WHERE dispatch_obligations.source_version < EXCLUDED.source_version
          AND dispatch_obligations.subject_type=EXCLUDED.subject_type
          AND dispatch_obligations.subject_ref=EXCLUDED.subject_ref
          AND dispatch_obligations.source=EXCLUDED.source
        RETURNING id
    """), {
        "id":str(uuid4()),"tenant":auth.tenant_id,"ref":body.external_ref,
        "kind":body.subject_type,"subject":body.subject_ref,"status":body.status,
        "balance":body.balance,"source":body.source,"evidence":body.evidence_ref,
        "version":body.source_version,"observed":body.observed_at,
    })
    if body.status!="open":
        await db.execute(text("""
            UPDATE dispatch_items SET status='blocked',
                last_error='obligation_not_open',updated_at=now()
            WHERE tenant_id=:tenant AND obligation_ref=:ref
              AND status IN ('queued','retry_wait','leased')
        """), {"tenant":auth.tenant_id,"ref":body.external_ref})
    await audit(
        db,tenant_id=auth.tenant_id,event_type="obligation.synced",
        details={"status":body.status,"source":body.source,"source_version":body.source_version,
                 "ref_hash":hashlib.sha256(body.external_ref.encode()).hexdigest()[:12]},
    )
    await db.commit()
    return {"accepted":True,"replayed":False,"status":body.status}


@router.post("/integrations/contacts")
async def upsert_external_contact(
    body: ContactSync,
    request: Request,
    auth: AuthContext = Depends(require_permission("data.import", allow_service_key=True)),
    db: AsyncSession = Depends(get_db),
):
    _require_connector(auth)
    await verify_source(
        db, tenant_id=auth.tenant_id,source=body.source,
        scope="contacts",request=request,
    )
    dest = normalize_destination(body.channel, body.recipient)
    if not dest:
        raise HTTPException(status_code=422, detail="Contato inválido.")
    try:
        ciphertext = encrypt_destination(dest)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    await bind_tenant(db, auth.tenant_id)
    suppressed = (await db.execute(text("""
        SELECT 1 FROM dispatch_suppressions
        WHERE tenant_id=:tenant AND subject_type='external' AND subject_ref=:ref
          AND channel IN ('all', :channel)
    """), {"tenant": auth.tenant_id, "ref": body.subject_ref,
             "channel": body.channel})).first()
    if suppressed and not body.opt_out:
        raise HTTPException(status_code=409, detail="Contato suprimido não pode ser reativado por sincronização.")
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
    request: Request,
    auth: AuthContext = Depends(require_permission("data.import", allow_service_key=True)),
    db: AsyncSession = Depends(get_db),
):
    """Idempotent financial facts from authoritative connectors, never from replies."""
    _require_connector(auth)
    await verify_source(
        db, tenant_id=auth.tenant_id,source=body.source,
        scope="financial",request=request,
    )
    _verified_observation(body.observed_at)
    if body.new_status=="paid" and body.balance!=0:
        raise HTTPException(status_code=422,detail="Pagamento integral exige saldo zero.")
    if body.new_status=="open" and body.balance<=0:
        raise HTTPException(status_code=422,detail="Pagamento parcial exige saldo positivo.")
    if body.amount_paid<=0:
        raise HTTPException(status_code=422,detail="Pagamento com valor não positivo.")
    await bind_tenant(db,auth.tenant_id)
    current=(await db.execute(text("""
        SELECT source,source_version,status,verified_at FROM dispatch_obligations
        WHERE tenant_id=:tenant AND external_ref=:ref FOR UPDATE
    """), {"tenant":auth.tenant_id,"ref":body.obligation_ref})).mappings().first()
    if not current or current["source"]!=body.source:
        raise HTTPException(status_code=404,detail="Dívida inexistente ou origem financeira incompatível.")
    previous=(await db.execute(text("""
        SELECT obligation_ref,source_version,amount_paid,evidence_ref,
               obligation_status,remaining_balance,paid_at
        FROM dispatch_payment_events
        WHERE tenant_id=:tenant AND source=:source AND source_event_id=:event
    """), {"tenant":auth.tenant_id,"source":body.source,
            "event":body.source_event_id})).mappings().first()
    if previous:
        if (previous["obligation_ref"]!=body.obligation_ref
            or previous["source_version"]!=body.source_version
            or previous["amount_paid"]!=body.amount_paid
            or previous["evidence_ref"]!=body.evidence_ref
            or previous["obligation_status"]!=body.new_status
            or previous["remaining_balance"]!=body.balance
            or previous["paid_at"]!=body.observed_at):
            raise HTTPException(status_code=409,detail="Evento já registrado com conteúdo diferente.")
        await db.commit()  # signed request remains protected against replay
        return {"accepted":True,"replayed":True}
    if body.source_version<=current["source_version"] or body.observed_at < current["verified_at"]:
        raise HTTPException(status_code=409,detail="Pagamento fora da ordem verificada da fonte.")
    if current["status"] in {"paid","disputed","agreement","cancelled"} and body.new_status=="open":
        raise HTTPException(status_code=409,detail="Não é permitido reabrir dívida encerrada por pagamento parcial.")
    await db.execute(text("""
        INSERT INTO dispatch_payment_events
            (id,tenant_id,obligation_ref,source,source_event_id,
             source_version,amount_paid,obligation_status,remaining_balance,
             evidence_ref,paid_at)
        VALUES (:id,:tenant,:ref,:source,:event,:version,:amount,:status,
                :balance,:evidence,:observed)
    """), {
        "id":str(uuid4()),"tenant":auth.tenant_id,"ref":body.obligation_ref,
        "source":body.source,"event":body.source_event_id,
        "version":body.source_version,"amount":body.amount_paid,
        "status":body.new_status,"balance":body.balance,
        "evidence":body.evidence_ref,"observed":body.observed_at,
    })
    await db.execute(text("""
        UPDATE dispatch_obligations
        SET source_version=:version,status=:status,balance=:balance,
            verified_at=:observed,evidence_ref=:evidence,updated_at=now()
        WHERE tenant_id=:tenant AND external_ref=:ref
    """), {
        "version":body.source_version,"status":body.new_status,
        "balance":body.balance,"observed":body.observed_at,
        "evidence":body.evidence_ref,"tenant":auth.tenant_id,
        "ref":body.obligation_ref,
    })
    if body.new_status!="open":
        await db.execute(text("""
            UPDATE dispatch_items SET status='blocked',
                last_error='paid_or_under_review',updated_at=now()
            WHERE tenant_id=:tenant AND obligation_ref=:ref
              AND status IN ('queued','retry_wait','leased')
        """), {"tenant":auth.tenant_id,"ref":body.obligation_ref})
    await audit(
        db,tenant_id=auth.tenant_id,event_type="payment.reconciled",
        details={"source":body.source,"status":body.new_status,
                 "version":body.source_version,
                 "event_hash":hashlib.sha256(body.source_event_id.encode()).hexdigest()[:12]},
    )
    await db.commit()
    return {"accepted":True,"replayed":False,"status":body.new_status}


class UncertainOutcomeReconciliation(BaseModel):
    source: str = Field(min_length=3,max_length=80)
    item_id: str = Field(min_length=1, max_length=80)
    provider: Literal["resend", "twilio"]
    status: Literal["sent", "failed"]
    evidence_ref: str = Field(min_length=10, max_length=200)
    provider_message_id: str | None = Field(default=None, max_length=200)


@router.post("/integrations/unknown-outcomes/reconcile")
async def reconcile_unknown_provider_outcome(
    body: UncertainOutcomeReconciliation,
    request: Request,
    auth: AuthContext = Depends(require_permission("data.import", allow_service_key=True)),
    db: AsyncSession = Depends(get_db),
):
    """A verified connector may resolve an UNKNOWN; never auto-requeue it."""
    _require_connector(auth)
    await verify_source(
        db, tenant_id=auth.tenant_id,source=body.source,
        scope="delivery",request=request,
    )
    if body.status == "sent" and not body.provider_message_id:
        raise HTTPException(status_code=422, detail="Envio confirmado precisa de ID do provedor.")
    await bind_tenant(db, auth.tenant_id)
    row = (await db.execute(text("""
        UPDATE dispatch_items
        SET status=:status, provider=:provider,
            provider_message_id=COALESCE(:message,provider_message_id),
            sent_at=CASE WHEN :status='sent' THEN now() ELSE sent_at END,
            last_error=NULL,updated_at=now()
        WHERE tenant_id=:tenant AND id=:item AND status='unknown'
        RETURNING campaign_id
    """), {
        "status": body.status, "provider": body.provider,
        "message": body.provider_message_id, "tenant": auth.tenant_id,
        "item": body.item_id,
    })).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=409, detail="Item não está em estado desconhecido.")
    digest = hashlib.sha256(body.evidence_ref.encode()).hexdigest()
    await audit(
        db, tenant_id=auth.tenant_id, campaign_id=str(row), item_id=body.item_id,
        event_type="outcome.reconciled",
        event_key=f"reconciliation:{body.item_id}:{digest[:32]}",
        details={"status": body.status, "provider": body.provider,
                 "evidence_hash": digest[:16]},
    )
    await db.commit()
    return {"accepted": True, "status": body.status}


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
    return await ingest_verified_event(provider=provider, event=event, raw=raw)


async def ingest_verified_event(
    *, provider: str, event: VerifiedGatewayEvent, raw: bytes,
) -> dict:
    """Used only after trusted gateway HMAC or native provider signature verification."""
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
            # Provider may call back before the sender transaction commits.
            # Persist only a normalized event, not message content or addresses.
            incoming_hash=hashlib.sha256(raw).hexdigest()
            prior=(await db.execute(text("""
                SELECT event_hash FROM dispatch_inbound
                WHERE tenant_id=:tenant AND provider=:provider AND external_event_id=:event
            """), {"tenant":event.tenant_id,"provider":provider,
                    "event":event.external_event_id})).scalar_one_or_none()
            if prior and prior!=incoming_hash:
                raise HTTPException(status_code=409,detail="Evento duplicado com conteúdo divergente.")
            if prior:
                return {"accepted":True,"replayed":True,"pending":True}
            kind_intent, kind_action = (
                classify_reply(event.message or "") if event.kind=="reply"
                else ("hard_bounce","suppress_email")
                if (provider=="resend" and event.kind=="failed" and
                    event.message in {"email.bounced","email.complained","email.suppressed"})
                else (None,None)
            )
            await db.execute(text("""
                INSERT INTO dispatch_inbound
                    (id,tenant_id,item_id,provider,provider_message_id,
                     external_event_id,event_hash,event_kind,reply_intent,recommended_action)
                VALUES (:id,:tenant,NULL,:provider,:message,:event,:hash,:kind,:intent,:action)
            """), {
                "id":str(uuid4()),"tenant":event.tenant_id,"provider":provider,
                "message":event.provider_message_id,"event":event.external_event_id,
                "hash":incoming_hash,"kind":event.kind,
                "intent":kind_intent,"action":kind_action,
            })
            await db.commit()
            return {"accepted":True,"pending":True}
        item = dict(found)
        existing = (await db.execute(text("""
            SELECT event_hash FROM dispatch_inbound
            WHERE tenant_id=:tenant AND provider=:provider AND external_event_id=:event
        """), {
            "tenant": event.tenant_id, "provider": provider,
            "event": event.external_event_id,
        })).scalar_one_or_none()
        payload_hash = hashlib.sha256(raw).hexdigest()
        if existing:
            if existing != payload_hash:
                raise HTTPException(status_code=409, detail="Evento de gateway reutilizado com payload diferente.")
            return {"accepted": True, "replayed": True}
        intent, action = (
            classify_reply(event.message or "")
            if event.kind == "reply"
            else ("hard_bounce", "suppress_email")
            if (provider=="resend" and event.kind=="failed" and
                event.message in {"email.bounced","email.complained","email.suppressed"})
            else (None,None)
        )
        await db.execute(text("""
            INSERT INTO dispatch_inbound
                (id,tenant_id,item_id,provider,provider_message_id,external_event_id,event_hash,
                 event_kind,reply_intent,recommended_action)
            VALUES (:id,:tenant,:item,:provider,:message,:event,:hash,:kind,:intent,:action)
        """), {
            "id": str(uuid4()), "tenant": event.tenant_id, "item": item["id"],
            "provider": provider, "message": event.provider_message_id,
            "event": event.external_event_id,
            "hash": payload_hash, "kind": event.kind,
            "intent": intent, "action": action,
        })
        target = {
            "delivered": "delivered", "read": "read",
            "reply": "replied", "failed": "failed",
        }[event.kind]
        rank = {"sent": 1, "delivered": 2, "read": 3, "replied": 4}
        # Gateway callbacks are not ordered. Never downgrade a prior receipt.
        if item["status"] in rank and (
            (target in rank and rank[target] > rank[item["status"]])
            or (target == "failed" and item["status"] == "sent")
        ):
            await db.execute(text("""
                UPDATE dispatch_items SET status=:status,updated_at=now()
                WHERE id=:id AND tenant_id=:tenant
            """), {"status": target, "id": item["id"], "tenant": event.tenant_id})
        if intent == "hard_bounce":
            await db.execute(text("""
                INSERT INTO dispatch_suppressions
                    (id,tenant_id,subject_type,subject_ref,channel,reason)
                VALUES (:id,:tenant,:kind,:ref,'email','hard_bounce')
                ON CONFLICT (tenant_id,subject_type,subject_ref,channel) DO NOTHING
            """), {"id":str(uuid4()),"tenant":event.tenant_id,
                    "kind":item["subject_type"],"ref":item["subject_ref"]})
            await db.execute(text("""
                UPDATE dispatch_items SET status='blocked',last_error='email_undeliverable',
                    updated_at=now()
                WHERE tenant_id=:tenant AND subject_type=:kind AND subject_ref=:ref
                  AND channel='email' AND status IN ('queued','retry_wait','leased')
            """), {"tenant":event.tenant_id,
                    "kind":item["subject_type"],"ref":item["subject_ref"]})
        if intent in {"opt_out", "wrong_recipient"}:
            await db.execute(text("""
                INSERT INTO dispatch_suppressions
                    (id,tenant_id,subject_type,subject_ref,channel,reason)
                VALUES (:id,:tenant,:kind,:ref,'all',:reason)
                ON CONFLICT (tenant_id,subject_type,subject_ref,channel) DO NOTHING
            """), {
                "id": str(uuid4()), "tenant": event.tenant_id,
                "kind": item["subject_type"], "ref": item["subject_ref"],
                "reason": intent,
            })
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
