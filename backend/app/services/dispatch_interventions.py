"""Individual retention/academic interventions and reusable template governance.

One user may start one *pre-approved* low-risk intervention. Collection and
segment/bulk campaigns retain four-eyes approval, with no direct-send bypass.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.dispatch_core import audit, bind_tenant


async def templates(db: AsyncSession, tenant_id: str) -> list[dict[str, Any]]:
    await bind_tenant(db, tenant_id)
    result = await db.execute(text("""
        SELECT id, code, version, purpose, channel, subject, body, status, created_by,
               approved_by, approved_at, created_at
        FROM dispatch_approved_templates
        WHERE tenant_id=:tenant
        ORDER BY created_at DESC LIMIT 100
    """), {"tenant": tenant_id})
    return [dict(row) for row in result.mappings()]


async def create_template(
    db: AsyncSession, *, tenant_id: str, actor: str, code: str,
    purpose: str, channel: str, subject: str, body: str,
) -> dict[str, Any]:
    if purpose not in {"retention", "academic", "service", "collections"}:
        raise ValueError("Finalidade não suportada.")
    if channel not in {"email", "sms", "whatsapp"}:
        raise ValueError("Canal não suportado.")
    if purpose == "collections" and channel == "whatsapp":
        raise ValueError("WhatsApp não é permitido para cobrança.")
    if not code.strip() or len(code)>100 or not subject.strip() or len(subject)>160 or not body.strip() or len(body)>2000:
        raise ValueError("Modelo inválido ou acima dos limites.")
    await bind_tenant(db, tenant_id)
    # Serialize versions for the same tenant/template code.
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
        {"key": f"dispatch:template:{tenant_id}:{code.strip()}"},
    )
    id_ = str(uuid4())
    result = await db.execute(text("""
        INSERT INTO dispatch_approved_templates
            (id,tenant_id,code,version,purpose,channel,subject,body,created_by)
        VALUES (
            :id,:tenant,:code,
            coalesce((SELECT max(version)+1 FROM dispatch_approved_templates
                     WHERE tenant_id=:tenant AND code=:code),1),
            :purpose,:channel,:subject,:body,:actor
        )
        RETURNING id,code,version,status
    """), {
        "id": id_, "tenant": tenant_id, "code": code.strip(), "purpose": purpose,
        "channel": channel, "subject": subject.strip(), "body": body, "actor": actor,
    })
    row = result.mappings().one()
    await audit(db, tenant_id=tenant_id, event_type="template.created",
                details={"id": id_, "actor": actor, "purpose": purpose, "channel": channel})
    await db.commit()
    return dict(row)


async def approve_template(
    db: AsyncSession, *, tenant_id: str, actor: str, template_id: str, evidence_ref: str,
) -> dict[str, Any]:
    if len(evidence_ref.strip()) < 8:
        raise ValueError("A aprovação exige referência de autorização institucional.")
    await bind_tenant(db, tenant_id)
    row = (await db.execute(text("""
        SELECT id, status, created_by, purpose, channel FROM dispatch_approved_templates
        WHERE tenant_id=:tenant AND id=:id FOR UPDATE
    """), {"tenant":tenant_id,"id":template_id})).mappings().first()
    if row is None:
        raise LookupError("Modelo não encontrado.")
    if row["status"] != "draft" or row["created_by"] == actor:
        raise ValueError("Modelo exige aprovação por pessoa diferente de quem o criou.")
    if row["purpose"] == "collections" and row["channel"] == "whatsapp":
        raise ValueError("WhatsApp não é permitido para cobrança.")
    await db.execute(text("""
        UPDATE dispatch_approved_templates
        SET status='approved', approved_by=:actor, approved_at=now(), approval_ref=:evidence
        WHERE tenant_id=:tenant AND id=:id
    """), {"tenant": tenant_id, "id": template_id, "actor": actor,
            "evidence": evidence_ref.strip()})
    await audit(db, tenant_id=tenant_id, event_type="template.approved",
                details={"id": template_id, "actor": actor})
    await db.commit()
    return {"id": template_id, "status": "approved"}


async def sync_authorization(
    db: AsyncSession, *, tenant_id: str, source: str, subject_type: str,
    subject_ref: str, channel: str, purpose: str, evidence_ref: str,
    status: str, verified_at: datetime, expires_at: datetime,
) -> dict[str, Any]:
    if purpose not in {"retention","academic","service","collections"}:
        raise ValueError("Finalidade inválida.")
    if channel not in {"email","sms","whatsapp"} or subject_type not in {"student","external"}:
        raise ValueError("Canal ou sujeito inválido.")
    if status not in {"granted","revoked","expired"}:
        raise ValueError("Estado de autorização inválido.")
    if not source or len(source)>80 or len(evidence_ref)<8 or len(evidence_ref)>200:
        raise ValueError("Origem ou evidência inválida.")
    if verified_at.tzinfo is None or expires_at.tzinfo is None:
        raise ValueError("Datas devem conter fuso horário.")
    if verified_at > datetime.now(timezone.utc)+timedelta(minutes=5):
        raise ValueError("Verificação não pode estar no futuro.")
    if status == "granted" and expires_at <= verified_at:
        raise ValueError("Autorização concedida exige validade posterior.")
    await bind_tenant(db, tenant_id)
    row = (await db.execute(text("""
        INSERT INTO dispatch_authorizations
            (id,tenant_id,subject_type,subject_ref,channel,purpose,
             source,evidence_ref,status,verified_at,expires_at)
        VALUES (:id,:tenant,:kind,:ref,:channel,:purpose,
                :source,:evidence,:status,:verified,:expiry)
        ON CONFLICT (tenant_id,subject_type,subject_ref,channel,purpose)
        DO UPDATE SET source=EXCLUDED.source, evidence_ref=EXCLUDED.evidence_ref,
          status=EXCLUDED.status, verified_at=EXCLUDED.verified_at,
          expires_at=EXCLUDED.expires_at, updated_at=now()
        WHERE dispatch_authorizations.verified_at < EXCLUDED.verified_at
        RETURNING id
    """), {
        "id": str(uuid4()), "tenant": tenant_id,
        "kind": subject_type, "ref": subject_ref,
        "channel": channel, "purpose": purpose,
        "source": source, "evidence": evidence_ref, "status": status,
        "verified": verified_at, "expiry": expires_at,
    })).scalar_one_or_none()
    if row is None:
        existing = (await db.execute(text("""
            SELECT evidence_ref,status,verified_at,expires_at,source
            FROM dispatch_authorizations
            WHERE tenant_id=:tenant AND subject_type=:kind AND subject_ref=:ref
              AND channel=:channel AND purpose=:purpose
        """), {
            "tenant":tenant_id,"kind":subject_type,"ref":subject_ref,
            "channel":channel,"purpose":purpose,
        })).mappings().first()
        if existing and (existing["evidence_ref"]==evidence_ref
                         and existing["status"]==status
                         and existing["verified_at"]==verified_at
                         and existing["expires_at"]==expires_at
                         and existing["source"]==source):
            return {"accepted":True,"status":status,"replayed":True}
        raise ValueError("Evento de autorização anterior ao registro atual.")
    if status != "granted":
        await db.execute(text("""
            UPDATE dispatch_items i SET status='blocked', last_error='contact_authorization_revoked',
                updated_at=now()
            FROM dispatch_campaigns c
            WHERE i.tenant_id=:tenant AND i.campaign_id=c.id AND c.tenant_id=i.tenant_id
              AND i.subject_type=:kind AND i.subject_ref=:ref
              AND i.channel=:channel AND c.purpose=:purpose
              AND i.status IN ('queued','retry_wait','leased')
        """), {
            "tenant": tenant_id, "kind": subject_type,
            "ref": subject_ref, "channel": channel, "purpose": purpose,
        })
    await audit(db, tenant_id=tenant_id, event_type="authorization.updated",
                details={"purpose": purpose, "channel": channel, "status": status, "source": source})
    await db.commit()
    return {"accepted": True, "status": status}


async def verified_authorization(
    db: AsyncSession, *, tenant_id: str, subject_type: str, subject_ref: str,
    channel: str, purpose: str, evidence_ref: str,
) -> bool:
    from app.core.config import get_settings

    sources = {part.strip() for part in
               get_settings().dispatch_trusted_authorization_sources.split(",") if part.strip()}
    if not sources:
        return False
    await bind_tenant(db, tenant_id)
    row = (await db.execute(text("""
        SELECT source FROM dispatch_authorizations
        WHERE tenant_id=:tenant AND subject_type=:kind AND subject_ref=:ref
          AND channel=:channel AND purpose=:purpose AND evidence_ref=:evidence
          AND status='granted' AND expires_at>now()
          AND verified_at>=now()-interval '90 days'
    """), {
        "tenant": tenant_id, "kind":subject_type, "ref":subject_ref,
        "channel":channel, "purpose":purpose, "evidence":evidence_ref,
    })).scalar_one_or_none()
    return row is not None and row in sources


async def create_intervention(
    db: AsyncSession, *, tenant_id: str, actor: str, template_id: str,
    subject_type: str, subject_ref: str, evidence_ref: str,
    idempotency_key: str, scheduled_for: datetime | None = None,
) -> dict[str, Any]:
    """Atomic, once-only low-risk message job: NO direct provider invocation."""
    if subject_type not in {"student","external"} or not subject_ref or len(subject_ref)>160:
        raise ValueError("Destinatário inválido.")
    if len(idempotency_key)<8 or len(idempotency_key)>128:
        raise ValueError("Idempotency-Key deve conter de 8 a 128 caracteres.")
    if not evidence_ref or len(evidence_ref)>200:
        raise ValueError("Evidência de autorização inválida.")
    if scheduled_for and scheduled_for.tzinfo is None:
        raise ValueError("Agendamento deve conter fuso horário.")
    await bind_tenant(db, tenant_id)
    payload={
        "actor":actor,"template_id":template_id,"subject_type":subject_type,
        "subject_ref":subject_ref,"evidence_ref":evidence_ref,
        "scheduled_for":scheduled_for.isoformat() if scheduled_for else None,
    }
    fingerprint=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
    claim_key=hashlib.sha256(f"{tenant_id}:{idempotency_key}".encode()).hexdigest()
    # Check before fetching current permissions: a network retry never
    # creates another job even if consent was revoked after original submit.
    previous=(await db.execute(text("""
        SELECT id,request_hash,status FROM dispatch_campaigns
        WHERE tenant_id=:tenant AND request_key=:key
    """), {"tenant":tenant_id,"key":claim_key})).mappings().first()
    if previous is not None:
        if previous["request_hash"]!=fingerprint:
            raise ValueError("Idempotency-Key já associada a outro conteúdo.")
        return {"id":str(previous["id"]),"status":previous["status"],"deduplicated":True}
    template=(await db.execute(text("""
        SELECT * FROM dispatch_approved_templates
        WHERE tenant_id=:tenant AND id=:id AND status='approved'
    """), {"tenant":tenant_id,"id":template_id})).mappings().first()
    if template is None:
        raise LookupError("Modelo aprovado não encontrado.")
    if template["purpose"] not in {"retention","academic","service"}:
        raise ValueError("Cobrança exige fluxo de campanha com aprovação independente.")
    if not await verified_authorization(
        db, tenant_id=tenant_id, subject_type=subject_type,subject_ref=subject_ref,
        channel=template["channel"],purpose=template["purpose"],
        evidence_ref=evidence_ref,
    ):
        raise ValueError("Autorização específica não verificada ou expirada.")
    blocked = (await db.execute(text("""
        SELECT 1 FROM dispatch_suppressions
        WHERE tenant_id=:tenant AND subject_type=:kind AND subject_ref=:ref
          AND channel IN ('all',:channel)
    """), {"tenant":tenant_id,"kind":subject_type,"ref":subject_ref,
            "channel":template["channel"]})).first()
    if blocked:
        raise ValueError("Destinatário bloqueado para comunicação.")
    if subject_type == "student":
        found=(await db.execute(text("""
            SELECT 1 FROM students WHERE tenant_id=:tenant AND id::text=:ref
            AND is_active IS TRUE AND communication_opt_out IS FALSE
        """), {"tenant":tenant_id,"ref":subject_ref})).first()
    else:
        found=(await db.execute(text("""
            SELECT 1 FROM dispatch_external_contacts
            WHERE tenant_id=:tenant AND subject_ref=:ref AND channel=:channel
            AND opt_out IS FALSE AND consent_ref=:evidence
        """), {"tenant":tenant_id,"ref":subject_ref,
                "channel":template["channel"],"evidence":evidence_ref})).first()
    if not found:
        raise ValueError("Contato não encontrado ou comunicação desautorizada.")
    now=datetime.now(timezone.utc)
    scheduled=scheduled_for if scheduled_for and scheduled_for>now else now
    campaign_id=str(uuid4())
    created=(await db.execute(text("""
        INSERT INTO dispatch_campaigns
            (id,tenant_id,name,purpose,channel,delivery_mode,
             request_key,request_hash,template_ref,template_body,status,
             authorization_ref,created_by,approved_by,approved_at,
             scheduled_for,per_minute_limit,daily_contact_limit)
        VALUES
            (:id,:tenant,:name,:purpose,:channel,'individual',
             :key,:hash,:ref,:body,:status,
             :evidence,:actor,:actor,now(),:scheduled,5,1)
        ON CONFLICT (tenant_id,request_key) WHERE request_key IS NOT NULL DO NOTHING
        RETURNING id
    """), {
        "id":campaign_id, "tenant":tenant_id, "name":"Intervenção individual",
        "purpose":template["purpose"],"channel":template["channel"],
        "key":claim_key,"hash":fingerprint,
        "ref":template["subject"],"body":template["body"],
        "status":"scheduled" if scheduled>now else "running",
        "evidence":evidence_ref,"actor":actor,"scheduled":scheduled,
    })).scalar_one_or_none()
    if created is None:
        existing=(await db.execute(text("""
            SELECT id,request_hash,status FROM dispatch_campaigns
            WHERE tenant_id=:tenant AND request_key=:key
        """), {"tenant":tenant_id,"key":claim_key})).mappings().one()
        if existing["request_hash"]!=fingerprint:
            raise ValueError("Idempotency-Key reutilizada para solicitação diferente.")
        await db.commit()
        return {"id":str(existing["id"]),"status":existing["status"],"deduplicated":True}
    item_id=str(uuid4())
    await db.execute(text("""
        INSERT INTO dispatch_items
            (id,tenant_id,campaign_id,subject_type,subject_ref,consent_ref,channel,scheduled_for)
        VALUES (:id,:tenant,:campaign,:kind,:ref,:evidence,:channel,:scheduled)
    """), {
        "id":item_id,"tenant":tenant_id,"campaign":campaign_id,"kind":subject_type,
        "ref":subject_ref,"evidence":evidence_ref,
        "channel":template["channel"],"scheduled":scheduled,
    })
    await audit(db,tenant_id=tenant_id,campaign_id=campaign_id,item_id=item_id,
                event_type="intervention.created",
                details={"actor":actor,"mode":"individual","purpose":template["purpose"]})
    await db.commit()
    return {"id":campaign_id,"status":"scheduled" if scheduled>now else "running",
            "deduplicated":False}
