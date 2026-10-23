"""Arquivamento agregado e expurgo de logs brutos de intervenção após o TTL."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import Date, cast, delete, func, literal_column, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.intervention import InterventionLog, InterventionLogDailyAggregate


async def purge_expired_intervention_logs(
    session: AsyncSession,
    *,
    now: datetime | None = None,
    retention_days: int | None = None,
    dry_run: bool = False,
) -> dict[str, object]:
    """Agrega por tenant/dia/estado/canal/risco/outcome e remove os detalhes antigos.

    Buckets usam sentinelas em vez de NULL para ter chave idempotente no PostgreSQL.
    O aggregate é atualizado por substituição (não incremento), evitando dupla contagem
    quando a execução é repetida antes de excluir logs antigos.
    """
    settings = get_settings()
    days = settings.intervention_log_retention_days if retention_days is None else retention_days
    if not 90 <= days <= 180:
        raise ValueError("retention_days precisa estar entre 90 e 180 dias.")
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)
    cutoff_day: date = current.date() - timedelta(days=days)
    cutoff = datetime.combine(cutoff_day, time.min, tzinfo=timezone.utc)

    # Reuse the identical expression objects in SELECT and GROUP BY. Rebuilding
    # COALESCE separately would produce distinct bind parameters in PostgreSQL.
    channel_bucket = func.coalesce(
        InterventionLog.channel, literal_column("'_none'")
    )
    risk_level_bucket = func.coalesce(
        InterventionLog.risk_level, literal_column("'_none'")
    )
    outcome_bucket = func.coalesce(
        InterventionLog.outcome, literal_column("'_none'")
    )
    metric_date = cast(InterventionLog.created_at, Date)
    grouped = (
        select(
            InterventionLog.tenant_id.label("tenant_id"),
            metric_date.label("metric_date"),
            InterventionLog.status.label("status"),
            channel_bucket.label("channel_bucket"),
            risk_level_bucket.label("risk_level_bucket"),
            outcome_bucket.label("outcome_bucket"),
            func.count(InterventionLog.id).label("event_count"),
        )
        .where(InterventionLog.created_at < cutoff)
        .group_by(
            InterventionLog.tenant_id,
            metric_date,
            InterventionLog.status,
            channel_bucket,
            risk_level_bucket,
            outcome_bucket,
        )
    )
    aggregates = (await session.execute(grouped)).mappings().all()
    expired_count = (
        await session.execute(
            select(func.count(InterventionLog.id)).where(InterventionLog.created_at < cutoff)
        )
    ).scalar_one()

    if dry_run:
        return {
            "dry_run": True,
            "retention_days": days,
            "cutoff_utc": cutoff.isoformat(),
            "expired_logs": int(expired_count or 0),
            "aggregate_buckets": len(aggregates),
            "deleted_logs": 0,
        }

    if aggregates:
        rows = [
            {
                **dict(row),
                "aggregated_at": current,
            }
            for row in aggregates
        ]
        statement = insert(InterventionLogDailyAggregate).values(rows)
        statement = statement.on_conflict_do_update(
            constraint="uq_intervention_log_daily_aggregate_key",
            set_={
                "event_count": statement.excluded.event_count,
                "aggregated_at": statement.excluded.aggregated_at,
            },
        )
        await session.execute(statement)

    result = await session.execute(delete(InterventionLog).where(InterventionLog.created_at < cutoff))
    deleted = int(result.rowcount or 0)
    await session.commit()
    return {
        "dry_run": False,
        "retention_days": days,
        "cutoff_utc": cutoff.isoformat(),
        "expired_logs": int(expired_count or 0),
        "aggregate_buckets": len(aggregates),
        "deleted_logs": deleted,
    }
