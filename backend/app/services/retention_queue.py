"""Fila Redis para execuções assíncronas da régua de retenção.

O payload não contém credenciais; apenas o tenant e os parâmetros da execução.
Jobs são idempotentes quando o cliente envia ``Idempotency-Key``.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from redis.asyncio import Redis

from app.core.config import get_settings

DELAYED_SUFFIX = ":delayed"
JOB_PREFIX = "beacon:retention:job:"
DEDUPE_PREFIX = "beacon:retention:dedupe:"
LOCK_SUFFIX = ":lock"
LIFECYCLE_LOCK_SUFFIX = ":lifecycle-lock"
_JOB_TERMINAL_STATES = frozenset({"completed", "failed", "dead_letter", "cancelled"})
_JOB_QUEUE_STATES = frozenset({"queued", "scheduled", "retrying"})
logger = logging.getLogger(__name__)


class RetentionJobLifecycleError(ValueError):
    """Raised when an execution cannot perform the requested lifecycle action."""


def _event(level: int, event_name: str, **fields: Any) -> None:
    """Log operacional estruturado sem payload, conteúdo de mensagens ou credenciais."""
    logger.log(level, event_name, extra={"event_name": event_name, **fields})


def _job_key(job_id: str) -> str:
    return f"{JOB_PREFIX}{job_id}"


def _encode(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def redis_client() -> Redis:
    settings = get_settings()
    return Redis.from_url(settings.redis_url, decode_responses=True)


async def enqueue_retention_job(
    *,
    tenant_id: str,
    tenant_slug: str | None,
    payload: dict[str, Any],
    idempotency_key: str | None = None,
    scheduled_at: datetime | str | float | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    redis = redis_client()
    try:
        if idempotency_key:
            dedupe_key = f"{DEDUPE_PREFIX}{tenant_id}:{idempotency_key}"
            existing = await redis.get(dedupe_key)
            if existing:
                job = await get_job(existing, tenant_id=tenant_id, redis=redis)
                if job:
                    _event(logging.INFO, "retention_job_deduplicated", job_id=job["id"], tenant_id=tenant_id, status=job.get("status"))
                    return {**job, "deduplicated": True}
                await redis.delete(dedupe_key)
            job_id = str(uuid4())
            claimed = await redis.set(
                dedupe_key, job_id, ex=settings.retention_job_ttl_seconds, nx=True
            )
            if not claimed:
                existing = await redis.get(dedupe_key)
                job = await get_job(existing, tenant_id=tenant_id, redis=redis) if existing else None
                if job:
                    _event(logging.INFO, "retention_job_deduplicated", job_id=job["id"], tenant_id=tenant_id, status=job.get("status"))
                    return {**job, "deduplicated": True}
                raise RuntimeError("Nao foi possivel reservar a chave de idempotencia")
        else:
            job_id = str(uuid4())

        now = time.time()
        scheduled_ts: float | None = None
        if isinstance(scheduled_at, datetime):
            schedule_dt = scheduled_at
            if schedule_dt.tzinfo is None:
                schedule_dt = schedule_dt.replace(tzinfo=timezone.utc)
            scheduled_ts = schedule_dt.timestamp()
        elif isinstance(scheduled_at, str):
            schedule_dt = datetime.fromisoformat(scheduled_at.replace("Z", "+00:00"))
            if schedule_dt.tzinfo is None:
                schedule_dt = schedule_dt.replace(tzinfo=timezone.utc)
            scheduled_ts = schedule_dt.timestamp()
        elif isinstance(scheduled_at, (int, float)):
            scheduled_ts = float(scheduled_at)
        is_scheduled = scheduled_ts is not None and scheduled_ts > now + 60
        initial_status = "scheduled" if is_scheduled else "queued"
        record = {
            "id": job_id,
            "tenant_id": tenant_id,
            "tenant_slug": tenant_slug or "",
            "payload": payload,
            "status": initial_status,
            "attempt": 0,
            "max_attempts": settings.retention_max_attempts,
            "created_at": now,
            "updated_at": now,
        }
        if is_scheduled and scheduled_ts is not None:
            record["scheduled_for"] = scheduled_ts
        await redis.hset(
            _job_key(job_id),
            mapping={
                "tenant_id": tenant_id,
                "tenant_slug": tenant_slug or "",
                "payload": _encode(payload),
                "status": initial_status,
                "attempt": "0",
                "max_attempts": str(settings.retention_max_attempts),
                "created_at": str(now),
                "updated_at": str(now),
                **({"scheduled_for": str(scheduled_ts)} if is_scheduled and scheduled_ts is not None else {}),
            },
        )
        await redis.expire(_job_key(job_id), settings.retention_job_ttl_seconds)
        if is_scheduled and scheduled_ts is not None:
            await redis.zadd(
                f"{settings.retention_queue_name}{DELAYED_SUFFIX}",
                {job_id: scheduled_ts},
            )
            _event(logging.INFO, "retention_job_scheduled", job_id=job_id, tenant_id=tenant_id, status="scheduled", scheduled_for=scheduled_ts)
        else:
            await redis.rpush(settings.retention_queue_name, job_id)
            _event(logging.INFO, "retention_job_enqueued", job_id=job_id, tenant_id=tenant_id, status="queued", attempt=0, deduplicated=False)
        return record
    finally:
        await redis.aclose()


async def get_job(
    job_id: str, *, tenant_id: str | None = None, redis: Redis | None = None
) -> dict[str, Any] | None:
    owns_client = redis is None
    client = redis or redis_client()
    try:
        raw = await client.hgetall(_job_key(job_id))
        if not raw or (tenant_id and raw.get("tenant_id") != tenant_id):
            return None
        result: dict[str, Any] = dict(raw)
        result["id"] = job_id
        for field in ("payload", "result"):
            if field in result:
                try:
                    result[field] = json.loads(result[field])
                except json.JSONDecodeError:
                    pass
        for field in ("attempt", "max_attempts"):
            if field in result:
                result[field] = int(result[field])
        for field in (
            "created_at",
            "updated_at",
            "next_retry_at",
            "scheduled_for",
            "paused_at",
            "resumed_at",
            "cancel_requested_at",
            "cancelled_at",
        ):
            if field in result:
                result[field] = float(result[field])
        return result
    finally:
        if owns_client:
            await client.aclose()


async def _update_job(redis: Redis, job_id: str, **fields: Any) -> None:
    fields["updated_at"] = str(time.time())
    encoded = {
        key: _encode(value) if isinstance(value, (dict, list)) else str(value)
        for key, value in fields.items()
    }
    await redis.hset(_job_key(job_id), mapping=encoded)


async def _remove_job_from_queues(redis: Redis, job_id: str) -> None:
    """Remove a job from both ready and delayed queues before changing state."""
    settings = get_settings()
    await redis.lrem(settings.retention_queue_name, 0, job_id)
    await redis.zrem(f"{settings.retention_queue_name}{DELAYED_SUFFIX}", job_id)


async def transition_retention_job(
    job_id: str,
    *,
    tenant_id: str,
    action: str,
) -> dict[str, Any] | None:
    """Apply an idempotent lifecycle action to a tenant-owned queue job.

    Queued, scheduled and retrying jobs can be paused or cancelled immediately.
    A running job accepts cancellation as ``cancel_requested``; the worker checks
    that request before starting and before publishing a completed result. A
    running job cannot be paused because the orchestrator may already be calling
    a provider and cannot safely roll back messages already sent.
    """
    if action not in {"pause", "resume", "cancel"}:
        raise RetentionJobLifecycleError(f"Ação de ciclo de vida desconhecida: {action}")

    redis = redis_client()
    lock_key = f"{_job_key(job_id)}{LIFECYCLE_LOCK_SUFFIX}"
    try:
        locked = await redis.set(lock_key, tenant_id, ex=30, nx=True)
        if not locked:
            raise RetentionJobLifecycleError("Outra operação já está alterando esta execução.")
        job = await get_job(job_id, tenant_id=tenant_id, redis=redis)
        if not job:
            return None
        current = str(job.get("status"))
        now = time.time()

        if action == "pause":
            if current == "paused":
                return job
            if current == "running":
                raise RetentionJobLifecycleError(
                    "Uma execução em andamento não pode ser pausada; aguarde sua conclusão ou cancele-a."
                )
            if current in _JOB_TERMINAL_STATES:
                raise RetentionJobLifecycleError(f"Execução já encerrada com estado {current}.")
            if current not in _JOB_QUEUE_STATES:
                raise RetentionJobLifecycleError(f"Não é possível pausar uma execução em estado {current}.")
            await _remove_job_from_queues(redis, job_id)
            await _update_job(redis, job_id, status="paused", paused_at=now)
            _event(logging.INFO, "retention_job_paused", job_id=job_id, tenant_id=tenant_id, previous_status=current)

        elif action == "resume":
            if current == "queued":
                return job
            if current != "paused":
                raise RetentionJobLifecycleError(f"Somente execuções pausadas podem ser retomadas (estado atual: {current}).")
            await _update_job(redis, job_id, status="queued", resumed_at=now)
            await redis.rpush(get_settings().retention_queue_name, job_id)
            _event(logging.INFO, "retention_job_resumed", job_id=job_id, tenant_id=tenant_id)

        else:  # cancel
            if current == "cancelled":
                return job
            if current in {"completed", "failed", "dead_letter"}:
                raise RetentionJobLifecycleError(f"Execução já encerrada com estado {current}.")
            if current == "running":
                await _update_job(redis, job_id, status="cancel_requested", cancel_requested_at=now)
                _event(logging.INFO, "retention_job_cancel_requested", job_id=job_id, tenant_id=tenant_id)
            else:
                await _remove_job_from_queues(redis, job_id)
                await _update_job(redis, job_id, status="cancelled", cancelled_at=now)
                _event(logging.INFO, "retention_job_cancelled", job_id=job_id, tenant_id=tenant_id, previous_status=current)

        return await get_job(job_id, tenant_id=tenant_id, redis=redis)
    finally:
        await redis.delete(lock_key)


async def _schedule_retry(redis: Redis, job_id: str, *, attempt: int, error: str, error_type: str | None = None) -> None:
    settings = get_settings()
    delay = settings.retention_retry_backoff_seconds * (2 ** max(0, attempt - 1))
    next_retry_at = time.time() + delay
    await _update_job(
        redis,
        job_id,
        status="retrying",
        attempt=attempt,
        last_error=error[:2000],
        next_retry_at=next_retry_at,
    )
    await redis.zadd(f"{settings.retention_queue_name}{DELAYED_SUFFIX}", {job_id: next_retry_at})
    _event(logging.WARNING, "retention_job_retry_scheduled", job_id=job_id, status="retrying", attempt=attempt, backoff_seconds=delay, error_type=error_type or "Exception")


async def process_retention_job(job_id: str, redis: Redis) -> bool:
    """Executa um job uma vez; retorna ``True`` quando deve ser considerado concluído."""
    settings = get_settings()
    job = await get_job(job_id, redis=redis)
    if not job or job.get("status") in _JOB_TERMINAL_STATES | {"paused"}:
        return True
    lock_key = f"{_job_key(job_id)}{LOCK_SUFFIX}"
    locked = await redis.set(lock_key, "1", ex=900, nx=True)
    if not locked:
        return False
    try:
        job = await get_job(job_id, redis=redis)
        if not job:
            return True
        if job.get("status") in _JOB_TERMINAL_STATES | {"paused", "cancel_requested"}:
            if job.get("status") == "cancel_requested":
                await _update_job(redis, job_id, status="cancelled", cancelled_at=time.time())
            return True
        attempt = int(job.get("attempt", 0)) + 1
        await _update_job(redis, job_id, status="running", attempt=attempt)
        _event(logging.INFO, "retention_job_started", job_id=job_id, tenant_id=job.get("tenant_id"), attempt=attempt, max_attempts=int(job.get("max_attempts", settings.retention_max_attempts)))
        try:
            from app.agents.orchestrator import RetentionOrchestrator
            from app.db.session import AsyncSessionLocal

            payload = job.get("payload", {})
            async with AsyncSessionLocal() as session:
                result = await RetentionOrchestrator(
                    session,
                    tenant_id=job["tenant_id"],
                    prefer_whatsapp_medio=bool(payload.get("prefer_whatsapp_medio", False)),
                ).run(
                    risk_levels=payload.get("risk_levels", ["critico"]),
                    batch_id=payload.get("batch_id"),
                    limit=int(payload.get("limit", 50)),
                    dry_run=payload.get("dry_run"),
                    channels=payload.get("channels"),
                    job_id=job_id,
                    campaign_id=payload.get("campaign_id"),
                    student_ids=payload.get("student_ids"),
                )
        except Exception as exc:
            if attempt < int(job.get("max_attempts", settings.retention_max_attempts)):
                await _schedule_retry(redis, job_id, attempt=attempt, error=str(exc), error_type=type(exc).__name__)
                return False
            await _update_job(
                redis,
                job_id,
                status="dead_letter",
                last_error=str(exc)[:2000],
                dead_lettered_at=time.time(),
            )
            await redis.rpush(settings.retention_dead_letter_queue_name, job_id)
            _event(logging.ERROR, "retention_job_dead_lettered", job_id=job_id, tenant_id=job.get("tenant_id"), status="dead_letter", attempt=attempt, max_attempts=int(job.get("max_attempts", settings.retention_max_attempts)), error_type=type(exc).__name__)
            return True
        latest = await get_job(job_id, redis=redis)
        if latest and latest.get("status") == "cancel_requested":
            await _update_job(redis, job_id, status="cancelled", cancelled_at=time.time(), result=result)
            _event(logging.INFO, "retention_job_cancelled_after_run", job_id=job_id, tenant_id=job.get("tenant_id"))
            return True
        await _update_job(redis, job_id, status="completed", result=result)
        _event(logging.INFO, "retention_job_completed", job_id=job_id, tenant_id=job.get("tenant_id"), status="completed", attempt=attempt)
        return True
    finally:
        await redis.delete(lock_key)


async def promote_due_retries(redis: Redis) -> int:
    settings = get_settings()
    delayed_key = f"{settings.retention_queue_name}{DELAYED_SUFFIX}"
    ids = await redis.zrangebyscore(delayed_key, min=0, max=time.time(), start=0, num=100)
    if not ids:
        return 0
    await redis.zrem(delayed_key, *ids)
    if ids:
        for job_id in ids:
            job = await get_job(job_id, redis=redis)
            if job and job.get("status") == "scheduled":
                await _update_job(redis, job_id, status="queued")
        await redis.rpush(settings.retention_queue_name, *ids)
        _event(logging.INFO, "retention_job_retries_promoted", queue_name=settings.retention_queue_name, count=len(ids))
    return len(ids)
