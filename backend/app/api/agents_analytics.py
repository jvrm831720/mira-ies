"""Retention analytics aggregates (delivery, engagement, cost, outcomes)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthContext, get_current_tenant
from app.core.config import get_settings
from app.db.session import get_db
from app.models.intervention import InterventionLog, ProviderCallMetric
from app.api.agents_common import router

_CHANNELS = ("whatsapp", "email", "sms")
_DELIVERED = {"delivered", "read", "clicked", "replied"}
_BOUNCE = {"failed", "rejected", "bounced", "invalid"}


@router.get("/agents/retention/analytics")
async def retention_analytics(
    days: int = Query(30, ge=1, le=365),
    auth: AuthContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Indicadores agregados por tenant: entrega, engajamento, custo e desfecho acadêmico."""
    settings = get_settings()
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    costs = {
        "whatsapp": float(settings.agents_cost_per_whatsapp_message_brl or 0),
        "email": float(settings.agents_cost_per_email_message_brl or 0),
        "sms": float(settings.agents_cost_per_sms_message_brl or 0),
    }

    rows = (
        await db.execute(
            select(
                InterventionLog.channel,
                InterventionLog.status,
                InterventionLog.delivery_status,
                InterventionLog.outcome,
                InterventionLog.student_id,
                func.count(InterventionLog.id),
            )
            .where(
                InterventionLog.tenant_id == auth.tenant_id,
                InterventionLog.created_at >= cutoff,
            )
            .group_by(
                InterventionLog.channel,
                InterventionLog.status,
                InterventionLog.delivery_status,
                InterventionLog.outcome,
                InterventionLog.student_id,
            )
        )
    ).all()

    channel_stats = {
        ch: {
            "messages_sent": 0,
            "delivered": 0,
            "bounced": 0,
            "engaged": 0,
            "students": set(),
            "retained_students": set(),
            "cost_brl": 0.0,
        }
        for ch in _CHANNELS
    }
    total_sent = 0
    students_contacted: set[str] = set()
    retained: set[str] = set()

    for channel, status, delivery_status, outcome, student_id, cnt in rows:
        ch = channel if channel in channel_stats else None
        if not ch:
            continue
        n = int(cnt or 0)
        if status in {"sent", "dry_run"}:
            channel_stats[ch]["messages_sent"] += n
            total_sent += n
            channel_stats[ch]["cost_brl"] += n * costs[ch]
            if student_id:
                channel_stats[ch]["students"].add(student_id)
                students_contacted.add(student_id)
        if delivery_status in _DELIVERED:
            channel_stats[ch]["delivered"] += n
            if delivery_status in {"clicked", "replied", "read"}:
                channel_stats[ch]["engaged"] += n
        if delivery_status in _BOUNCE or status == "failed":
            channel_stats[ch]["bounced"] += n
        if outcome == "stayed" and student_id:
            channel_stats[ch]["retained_students"].add(student_id)
            retained.add(student_id)

    latency_rows = (
        await db.execute(
            select(
                ProviderCallMetric.channel,
                ProviderCallMetric.provider,
                func.avg(ProviderCallMetric.latency_ms),
                func.count(ProviderCallMetric.id),
            )
            .where(
                ProviderCallMetric.tenant_id == auth.tenant_id,
                ProviderCallMetric.occurred_at >= cutoff,
            )
            .group_by(ProviderCallMetric.channel, ProviderCallMetric.provider)
        )
    ).all()
    providers = [
        {
            "channel": ch,
            "provider": prov,
            "average_latency_ms": float(avg_lat) if avg_lat is not None else None,
            "attempts": int(attempts or 0),
        }
        for ch, prov, avg_lat, attempts in latency_rows
    ]

    channels_out = {}
    for ch, st in channel_stats.items():
        sent = st["messages_sent"]
        delivered = st["delivered"]
        engaged = st["engaged"]
        channels_out[ch] = {
            "messages_sent": sent,
            "delivery_rate_pct": round((delivered / sent) * 100, 1) if sent else 0.0,
            "engagement_rate_pct": round((engaged / sent) * 100, 1) if sent else 0.0,
            "bounce_rate_pct": round((st["bounced"] / sent) * 100, 1) if sent else 0.0,
            "estimated_cost_brl": round(st["cost_brl"], 4),
            "unique_students_contacted": len(st["students"]),
            "attribution": {"retained_students": len(st["retained_students"])},
            "average_latency_ms": next(
                (p["average_latency_ms"] for p in providers if p["channel"] == ch),
                None,
            ),
        }

    return {
        "period_days": days,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "messages_sent": total_sent,
            "unique_students_contacted": len(students_contacted),
            "retained_students": len(retained),
            "retention_rate_pct": round((len(retained) / len(students_contacted)) * 100, 1)
            if students_contacted
            else 0.0,
            "estimated_cost_brl_total": round(
                sum(st["cost_brl"] for st in channel_stats.values()), 4
            ),
        },
        "channels": channels_out,
        "providers": providers,
    }
