"""Fila Redis para execuções assíncronas da régua de retenção.

O payload não contém credenciais; apenas o tenant e os parâmetros da execução.
Jobs são idempotentes quando o cliente envia ``Idempotency-Key``.
"""
from __future__ import annotations

import json
import time
from typing import Any
from uuid import uuid4

from redis.asyncio import Redis

from app.core.config import get_settings

DELAYED_SUFFIX = ":delayed"
JOB_PREFIX = "beacon:retention:job:"
DEDUPE_PREFIX = "beacon:retention:dedupe:"
LOCK_SUFFIX = ":lock"


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
                    return {**job, "deduplicated": True}
                raise RuntimeError("Nao foi possivel reservar a chave de idempotencia")
        else:
            job_id = str(uuid4())

        now = time.time()
        record = {
            "id": job_id,
            "tenant_id": tenant_id,
            "tenant_slug": tenant_slug or "",
            "payload": payload,
            "status": "queued",
            "attempt": 0,
            "max_attempts": settings.retention_max_attempts,
            "created_at": now,
            "updated_at": now,
        }
        await redis.hset(
            _job_key(job_id),
            mapping={
                "tenant_id": tenant_id,
                "tenant_slug": tenant_slug or "",
                "payload": _encode(payload),
                "status": "queued",
                "attempt": "0",
                "max_attempts": str(settings.retention_max_attempts),
                "created_at": str(now),
                "updated_at": str(now),
            },
        )
        await redis.expire(_job_key(job_id), settings.retention_job_ttl_seconds)
        await redis.rpush(settings.retention_queue_name, job_id)
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
        for field in ("created_at", "updated_at", "next_retry_at"):
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


async def _schedule_retry(redis: Redis, job_id: str, *, attempt: int, error: str) -> None:
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


async def process_retention_job(job_id: str, redis: Redis) -> bool:
    """Executa um job uma vez; retorna ``True`` quando deve ser considerado concluído."""
    settings = get_settings()
    job = await get_job(job_id, redis=redis)
    if not job or job.get("status") in {"completed", "failed", "dead_letter"}:
        return True
    lock_key = f"{_job_key(job_id)}{LOCK_SUFFIX}"
    locked = await redis.set(lock_key, "1", ex=900, nx=True)
    if not locked:
        return False
    try:
        job = await get_job(job_id, redis=redis)
        if not job:
            return True
        attempt = int(job.get("attempt", 0)) + 1
        await _update_job(redis, job_id, status="running", attempt=attempt)
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
                )
        except Exception as exc:
            if attempt < int(job.get("max_attempts", settings.retention_max_attempts)):
                await _schedule_retry(redis, job_id, attempt=attempt, error=str(exc))
                return False
            await _update_job(
                redis,
                job_id,
                status="dead_letter",
                last_error=str(exc)[:2000],
                dead_lettered_at=time.time(),
            )
            await redis.rpush(settings.retention_dead_letter_queue_name, job_id)
            return True
        await _update_job(redis, job_id, status="completed", result=result)
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
        await redis.rpush(settings.retention_queue_name, *ids)
    return len(ids)
