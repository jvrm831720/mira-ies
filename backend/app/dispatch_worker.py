"""Independent PostgreSQL dispatcher: SKIP LOCKED, lease fencing, recovery.

Start manually via: python -m app.dispatch_worker --once
No real send unless DISPATCH_LIVE_ENABLED + live tenant and channel allowlists.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import json
import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.services.dispatch_core import audit, bind_tenant
from app.services.provider_guard import acquire_send_slot, record_provider_outcome
from app.services.dispatch_delivery import (
    DeliveryResult, allow_rate, eligibility, send_authorized, live_enabled,
)

logger = logging.getLogger(__name__)
MAX_BATCH = 25
LEASE_SECONDS = 120
TRANSIENT_REASONS = {"outside_contact_window", "daily_contact_cap"}


async def active_tenants() -> list[str]:
    # Global tenant lookup is not a dispatch table. RLS is set before each
    # tenant-specific query; workers never require BYPASSRLS.
    async with AsyncSessionLocal() as db:
        rows = await db.execute(text("SELECT id FROM tenants WHERE is_active IS TRUE ORDER BY id"))
        return [str(row[0]) for row in rows]


async def promote_due_campaigns(db, tenant_id: str) -> int:
    await bind_tenant(db, tenant_id)
    rows = (await db.execute(text("""
        UPDATE dispatch_campaigns
        SET status='running', updated_at=now()
        WHERE tenant_id=:tenant AND status='scheduled'
          AND approved_at IS NOT NULL AND authorization_ref IS NOT NULL
          AND scheduled_for<=now()
        RETURNING id
    """), {"tenant": tenant_id})).scalars().all()
    for campaign_id in rows:
        await audit(db, tenant_id=tenant_id, campaign_id=str(campaign_id),
                    event_type="campaign.auto_started")
    await db.commit()
    return len(rows)


async def recover_expired_leases(db, tenant_id: str) -> dict[str, int]:
    """Leased (not yet sending) may be reclaimed; sending becomes UNKNOWN."""
    await bind_tenant(db, tenant_id)
    leased = (await db.execute(text("""
        UPDATE dispatch_items
        SET status='queued', lease_token=NULL, lease_until=NULL, lease_owner=NULL,
            updated_at=now()
        WHERE tenant_id=:tenant AND status='leased' AND lease_until < now()
        RETURNING id,campaign_id
    """), {"tenant": tenant_id})).mappings().all()
    for row in leased:
        await audit(db, tenant_id=tenant_id, campaign_id=str(row["campaign_id"]),
                    item_id=str(row["id"]), event_type="item.lease_recovered")
    unknown = (await db.execute(text("""
        UPDATE dispatch_items
        SET status='unknown', lease_token=NULL, lease_until=NULL,
            lease_owner=NULL, last_error='provider_outcome_unknown', updated_at=now()
        WHERE tenant_id=:tenant AND status='sending' AND lease_until < now()
        RETURNING id,campaign_id
    """), {"tenant": tenant_id})).mappings().all()
    for row in unknown:
        await audit(db, tenant_id=tenant_id, campaign_id=str(row["campaign_id"]),
                    item_id=str(row["id"]), event_type="item.unknown_outcome")
    await db.commit()
    for campaign_id in {str(row["campaign_id"]) for row in unknown}:
        await _auto_pause(db, tenant_id, campaign_id)
    return {"requeued": len(leased), "unknown": len(unknown)}


async def claim_batch(db, tenant_id: str, owner: str, limit: int = MAX_BATCH) -> list[dict]:
    if not 1 <= limit <= MAX_BATCH:
        raise ValueError("Limite de claim fora do intervalo.")
    await bind_tenant(db, tenant_id)
    token = str(uuid4())
    result = await db.execute(text("""
        WITH chosen AS (
            SELECT i.id FROM dispatch_items i
            JOIN dispatch_campaigns c ON c.id=i.campaign_id AND c.tenant_id=i.tenant_id
            WHERE i.tenant_id=:tenant
              AND i.status IN ('queued','retry_wait')
              AND i.scheduled_for <= now()
              AND (i.next_attempt_at IS NULL OR i.next_attempt_at <= now())
              AND c.status='running'
              AND c.approved_at IS NOT NULL
              AND c.authorization_ref IS NOT NULL
            ORDER BY i.scheduled_for, i.created_at, i.id
            FOR UPDATE OF i SKIP LOCKED
            LIMIT :limit
        )
        UPDATE dispatch_items i
        SET status='leased', lease_owner=:owner, lease_token=:token,
            lease_until=now() + interval '120 seconds', updated_at=now()
        FROM chosen WHERE i.id=chosen.id AND i.tenant_id=:tenant
        RETURNING i.id, i.campaign_id, i.lease_token
    """), {
        "tenant": tenant_id, "owner": owner, "token": token, "limit": limit,
    })
    claimed = [dict(row) for row in result.mappings().all()]
    await db.commit()
    return claimed


async def _finalize(
    db, *, tenant_id: str, item_id: str, token: str,
    status: str, reason: str | None = None, provider: str | None = None,
    provider_message_id: str | None = None, next_attempt_at=None,
) -> bool:
    await bind_tenant(db, tenant_id)
    row = (await db.execute(text("""
        UPDATE dispatch_items
        SET status=:status, last_error=:reason,
            provider=COALESCE(:provider,provider),
            provider_message_id=COALESCE(:provider_id,provider_message_id),
            next_attempt_at=:next_attempt,
            sent_at=CASE WHEN :status='sent' THEN now() ELSE sent_at END,
            lease_token=NULL,lease_until=NULL,lease_owner=NULL,updated_at=now()
        WHERE tenant_id=:tenant AND id=:id AND lease_token=:token
          AND status IN ('leased','sending')
        RETURNING id,campaign_id
    """), {
        "tenant": tenant_id, "id": item_id, "token": token,
        "status": status, "reason": reason, "provider": provider,
        "provider_id": provider_message_id, "next_attempt": next_attempt_at,
    })).mappings().first()
    if row is not None:
        await audit(db, tenant_id=tenant_id, item_id=item_id,
                    campaign_id=str(row["campaign_id"]), event_type=f"item.{status}",
                    details={"reason_code": (reason or "")[:80], "provider": provider})
    await db.commit()
    return row is not None


async def _auto_pause(db, tenant_id: str, campaign_id: str) -> None:
    """Pause on >=3 unknowns or >=30% definite failures among >=10 recent outcomes."""
    await bind_tenant(db, tenant_id)
    row = (await db.execute(text("""
        SELECT count(*) AS total,
               count(*) FILTER (WHERE status IN ('failed','unknown')) AS failed,
               count(*) FILTER (WHERE status='unknown') AS unknown
        FROM (
            SELECT status FROM dispatch_items
            WHERE tenant_id=:tenant AND campaign_id=:campaign
              AND status IN ('sent','delivered','read','replied','failed','unknown')
            ORDER BY updated_at DESC LIMIT 50
        ) recent
    """), {"tenant": tenant_id, "campaign": campaign_id})).mappings().one()
    count, failures, uncertain = int(row["total"]), int(row["failed"]), int(row["unknown"])
    if uncertain < 3 and (count < 10 or failures / count < 0.30):
        return
    paused = (await db.execute(text("""
        UPDATE dispatch_campaigns SET status='paused', paused_reason='quality_guard',
            updated_at=now() WHERE tenant_id=:tenant AND id=:campaign
              AND status='running' RETURNING id
    """), {"tenant": tenant_id, "campaign": campaign_id})).scalar_one_or_none()
    if paused:
        await audit(db, tenant_id=tenant_id, campaign_id=campaign_id,
                    event_type="campaign.auto_paused",
                    details={"failures": failures, "sample": count, "unknown": uncertain})
    await db.commit()


async def process_item(
    *, tenant_id: str, item_id: str, token: str, owner: str,
) -> str:
    async with AsyncSessionLocal() as db:
        await bind_tenant(db, tenant_id)
        # Lock campaign first: serialize pause/cancel with send initiation.
        item_row = (await db.execute(text("""
            SELECT campaign_id FROM dispatch_items
            WHERE tenant_id=:tenant AND id=:id AND lease_token=:token AND status='leased'
        """), {"tenant": tenant_id, "id": item_id, "token": token})).first()
        if not item_row:
            return "stale"
        campaign_id = str(item_row[0])
        campaign = (await db.execute(text("""
            SELECT * FROM dispatch_campaigns WHERE tenant_id=:tenant AND id=:campaign FOR UPDATE
        """), {"tenant": tenant_id, "campaign": campaign_id})).mappings().first()
        item = (await db.execute(text("""
            SELECT * FROM dispatch_items WHERE tenant_id=:tenant AND id=:id FOR UPDATE
        """), {"tenant": tenant_id, "id": item_id})).mappings().first()
        if not campaign or not item or item["status"] != "leased" or str(item["lease_token"]) != token:
            await db.rollback()
            return "stale"
        camp, record = dict(campaign), dict(item)
        # Serialize concurrent campaigns addressing the same recipient.
        # The competing worker sees this item as 'sending' after commit,
        # so the 24-hour contact limit cannot be bypassed by simultaneous claims.
        await db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": (
                f"dispatch:contact:{tenant_id}:{record['subject_type']}:"
                f"{record['subject_ref']}:{record['channel']}"
            )},
        )
        decision = await eligibility(db, tenant_id=tenant_id, campaign=camp, item=record)
        if not decision.allowed:
            if decision.reason in TRANSIENT_REASONS:
                due = datetime.now(timezone.utc) + timedelta(
                    hours=24 if decision.reason == "daily_contact_cap" else 1
                )
                await _finalize(db, tenant_id=tenant_id, item_id=item_id,
                                token=token, status="retry_wait", reason=decision.reason,
                                next_attempt_at=due)
                return "retry_wait"
            await _finalize(db, tenant_id=tenant_id, item_id=item_id,
                            token=token, status="blocked", reason=decision.reason)
            return "blocked"
        if not await allow_rate(db, tenant_id=tenant_id, channel=camp["channel"],
                                campaign_id=campaign_id,
                                campaign_rpm=camp["per_minute_limit"]):
            await _finalize(db, tenant_id=tenant_id, item_id=item_id, token=token,
                            status="retry_wait", reason="rate_limit",
                            next_attempt_at=datetime.now(timezone.utc)+timedelta(seconds=30))
            return "retry_wait"
        if live_enabled(tenant_id, camp["channel"]):
            provider = "resend" if camp["channel"] == "email" else "twilio"
            decision_guard = await acquire_send_slot(
                tenant_id=tenant_id, channel=camp["channel"], provider=provider,
            )
            if not decision_guard.allowed:
                await _finalize(db, tenant_id=tenant_id, item_id=item_id, token=token,
                                status="retry_wait", reason="provider_guard_unavailable",
                                next_attempt_at=datetime.now(timezone.utc) + timedelta(seconds=60))
                return "retry_wait"
        moved = (await db.execute(text("""
            UPDATE dispatch_items SET status='sending', attempt=attempt+1,
                lease_until=now()+interval '120 seconds', updated_at=now()
            WHERE tenant_id=:tenant AND id=:id AND lease_token=:token AND status='leased'
            RETURNING attempt
        """), {"tenant": tenant_id, "id": item_id, "token": token})).scalar_one_or_none()
        if moved is None:
            await db.rollback()
            return "stale"
        await db.commit()
        attempts = int(moved)

    # No transaction is held open while waiting on an external provider.
    # Pre-send crash recovery marks the outcome UNKNOWN rather than resending.
    started = time.monotonic()
    try:
        result: DeliveryResult = await send_authorized(
            tenant_id=tenant_id, campaign=camp, item=record,
            destination=decision.destination or "", display_name=decision.display_name,
        )
    except Exception:
        # A network failure can be ambiguous: NEVER automatically re-send.
        result = DeliveryResult("unknown", "unavailable", error_code="provider_outcome_unknown")

    if live_enabled(tenant_id, camp["channel"]):
        try:
            await record_provider_outcome(
                provider=result.provider, success=result.status == "sent",
                ambiguous=result.status == "unknown",
                latency_seconds=time.monotonic() - started,
            )
        except Exception:
            logger.exception("dispatch_provider_guard_telemetry_failed")
    status = result.status
    next_attempt_at = None
    if status == "failed" and result.retryable and attempts < 3:
        status = "retry_wait"
        next_attempt_at = datetime.now(timezone.utc) + timedelta(seconds=30 * (2 ** (attempts - 1)))

    async with AsyncSessionLocal() as db:
        finalized = await _finalize(
            db, tenant_id=tenant_id, item_id=item_id, token=token,
            status=status, reason=result.error_code, provider=result.provider,
            provider_message_id=result.provider_message_id,
            next_attempt_at=next_attempt_at,
        )
        if finalized and status in {"unknown","failed"}:
            await _auto_pause(db, tenant_id, campaign_id)
        return status if finalized else "stale"


async def complete_drained_campaigns(db, tenant_id: str) -> int:
    await bind_tenant(db, tenant_id)
    rows = (await db.execute(text("""
        UPDATE dispatch_campaigns c SET status='completed', updated_at=now()
        WHERE c.tenant_id=:tenant AND c.status='running'
          AND EXISTS (SELECT 1 FROM dispatch_items i WHERE i.tenant_id=:tenant AND i.campaign_id=c.id)
          AND NOT EXISTS (
              SELECT 1 FROM dispatch_items i WHERE i.tenant_id=:tenant
                AND i.campaign_id=c.id AND i.status IN ('queued','retry_wait','leased','sending')
          ) RETURNING c.id
    """), {"tenant": tenant_id})).scalars().all()
    for campaign_id in rows:
        await audit(db, tenant_id=tenant_id, campaign_id=str(campaign_id),
                    event_type="campaign.completed")
    await db.commit()
    return len(rows)


async def write_heartbeat(db, *, tenant_id: str, owner: str, counts: dict[str, int]) -> None:
    await bind_tenant(db, tenant_id)
    await db.execute(text("""
        INSERT INTO dispatch_worker_heartbeats (tenant_id,worker_id,seen_at,stats)
        VALUES (:tenant,:worker,now(),CAST(:stats AS jsonb))
        ON CONFLICT (tenant_id,worker_id)
        DO UPDATE SET seen_at=now(),stats=EXCLUDED.stats
    """), {"tenant": tenant_id, "worker": owner, "stats": json.dumps(counts)})
    await db.commit()


async def run_round(*, owner: str, max_batch: int = 10, parallel: int = 3) -> dict[str, int]:
    max_batch = max(1, min(MAX_BATCH, max_batch))
    parallel = max(1, min(8, parallel))
    summary: dict[str, int] = {}
    semaphore = asyncio.Semaphore(parallel)

    async def guarded(tenant_id: str, record: dict) -> None:
        async with semaphore:
            try:
                result = await process_item(
                    tenant_id=tenant_id, item_id=str(record["id"]),
                    token=str(record["lease_token"]), owner=owner,
                )
            except Exception:
                # Failure before provider execution leaves a leased item recoverable.
                # Failure after sending leaves a fenced 'sending' item, later UNKNOWN.
                logger.exception("dispatch_item_processing_failed", extra={
                    "item_id": str(record["id"]), "tenant_id": tenant_id,
                })
                result = "worker_error"
            summary[result] = summary.get(result, 0) + 1

    for tenant_id in await active_tenants():
        async with AsyncSessionLocal() as db:
            await promote_due_campaigns(db, tenant_id)
            recovered = await recover_expired_leases(db, tenant_id)
            summary["recovered"] = summary.get("recovered", 0) + recovered["requeued"]
            summary["uncertain_recovered"] = summary.get("uncertain_recovered", 0) + recovered["unknown"]
            claimed = await claim_batch(db, tenant_id, owner, limit=max_batch)
        await asyncio.gather(*(guarded(tenant_id, record) for record in claimed))
        async with AsyncSessionLocal() as db:
            summary["completed"] = summary.get("completed", 0) + await complete_drained_campaigns(db, tenant_id)
            await write_heartbeat(db, tenant_id=tenant_id, owner=owner,
                                  counts={"claimed": len(claimed), "completed": summary.get("completed", 0)})
    return summary


async def run_worker(*, once: bool, interval: float, parallel: int) -> None:
    owner = f"mira-{uuid4()}"
    while True:
        try:
            summary = await run_round(owner=owner, parallel=parallel)
            logger.info("dispatch_round", extra={"counts": summary, "owner": owner})
        except Exception:
            logger.exception("dispatch_worker_round_failed")
            if once:
                raise
        if once:
            break
        await asyncio.sleep(max(1.0, interval))


def main() -> None:
    parser = argparse.ArgumentParser(description="MIRA Dispatch — safe outbox worker")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=float, default=3.0)
    parser.add_argument("--parallel", type=int, default=3)
    args = parser.parse_args()
    if not get_settings().dispatch_worker_enabled:
        raise SystemExit("DISPATCH_WORKER_ENABLED=false; worker permanece desligado.")
    asyncio.run(run_worker(once=args.once, interval=args.interval, parallel=args.parallel))


if __name__ == "__main__":
    main()
