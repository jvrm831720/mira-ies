"""Reconcile native callbacks that arrived before message-id publication.

Provider callbacks are durably stored as metadata and attached after the
accepted message is visible. No webhook triggers a second send.
"""
from __future__ import annotations

from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.student import Student
from app.services.consent import apply_preference_changes
from app.services.dispatch_core import audit, bind_tenant


async def reconcile_pending_receipts(
    db: AsyncSession, *, tenant_id: str, limit: int = 100,
) -> int:
    await bind_tenant(db, tenant_id)
    rows=(await db.execute(text("""
        SELECT e.id AS receipt_id,e.event_kind,e.reply_intent,
               e.recommended_action,e.provider,e.external_event_id,
               i.id AS item_id,i.campaign_id,i.subject_type,i.subject_ref,
               i.obligation_ref,i.channel,i.status
        FROM dispatch_inbound e
        JOIN dispatch_items i ON
            i.tenant_id=e.tenant_id AND i.provider=e.provider
            AND i.provider_message_id=e.provider_message_id
        WHERE e.tenant_id=:tenant AND e.item_id IS NULL
          AND i.status IN ('sent','delivered','read','replied','failed')
        ORDER BY e.occurred_at,e.id
        FOR UPDATE OF e SKIP LOCKED LIMIT :limit
    """), {"tenant":tenant_id,"limit":max(1,min(limit,500))})).mappings().all()
    rank={"sent":1,"delivered":2,"read":3,"replied":4}
    applied=0
    for event in rows:
        item_id=str(event["item_id"])
        await db.execute(text("""
            UPDATE dispatch_inbound SET item_id=:item
            WHERE tenant_id=:tenant AND id=:receipt AND item_id IS NULL
        """), {"tenant":tenant_id,"item":item_id,"receipt":event["receipt_id"]})
        target={
            "delivered":"delivered","read":"read","reply":"replied","failed":"failed",
        }.get(event["event_kind"])
        status=event["status"]
        if status in rank and (
            (target in rank and rank[target]>rank[status])
            or (target=="failed" and status=="sent")
        ):
            await db.execute(text("""
                UPDATE dispatch_items SET status=:status,updated_at=now()
                WHERE tenant_id=:tenant AND id=:item
            """), {"tenant":tenant_id,"item":item_id,"status":target})
        intent=event["reply_intent"]
        if intent in {"opt_out","wrong_recipient","hard_bounce"}:
            channel="email" if intent=="hard_bounce" else "all"
            await db.execute(text("""
                INSERT INTO dispatch_suppressions
                    (id,tenant_id,subject_type,subject_ref,channel,reason)
                VALUES (:id,:tenant,:kind,:ref,:channel,:reason)
                ON CONFLICT (tenant_id,subject_type,subject_ref,channel) DO NOTHING
            """), {
                "id":str(uuid4()),"tenant":tenant_id,
                "kind":event["subject_type"],"ref":event["subject_ref"],
                "channel":channel,"reason":intent,
            })
            if intent in {"opt_out","wrong_recipient"}:
                if event["subject_type"]=="external":
                    await db.execute(text("""
                        UPDATE dispatch_external_contacts SET opt_out=TRUE
                        WHERE tenant_id=:tenant AND subject_ref=:ref
                    """), {"tenant":tenant_id,"ref":event["subject_ref"]})
                else:
                    student=(await db.execute(select(Student).where(
                        Student.tenant_id==tenant_id,Student.id==event["subject_ref"],
                    ))).scalar_one_or_none()
                    if student:
                        apply_preference_changes(
                            db,tenant_id=tenant_id,student=student,opt_out=True,
                            source="dispatch_gateway",method="verified_webhook",
                            location="/api/v1/dispatch/native",
                            source_reference=event["external_event_id"],
                        )
            await db.execute(text("""
                UPDATE dispatch_items SET status='blocked',
                    last_error='recipient_suppressed',updated_at=now()
                WHERE tenant_id=:tenant AND subject_type=:kind AND subject_ref=:ref
                  AND (:channel='all' OR channel=:channel)
                  AND status IN ('queued','retry_wait','leased')
            """), {
                "tenant":tenant_id,"kind":event["subject_type"],
                "ref":event["subject_ref"],"channel":channel,
            })
        elif intent in {"claims_paid","dispute"} and event["obligation_ref"]:
            await db.execute(text("""
                UPDATE dispatch_items SET status='blocked',
                    last_error='financial_review_needed',updated_at=now()
                WHERE tenant_id=:tenant AND obligation_ref=:obligation
                  AND status IN ('queued','retry_wait','leased')
            """), {"tenant":tenant_id,"obligation":event["obligation_ref"]})
        await audit(
            db,tenant_id=tenant_id,campaign_id=str(event["campaign_id"]),
            item_id=item_id,event_type=f"gateway.{event['event_kind']}",
            event_key=f"gateway:{event['provider']}:{event['external_event_id']}",
            details={"intent":intent,"action":event["recommended_action"],
                     "provider":event["provider"],"reconciled":True},
        )
        applied+=1
    if applied:
        await db.commit()
    return applied
