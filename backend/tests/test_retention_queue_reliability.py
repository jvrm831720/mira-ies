"""Reliability tests for Redis retention jobs using an isolated fake Redis."""
from __future__ import annotations
import json
import logging
import time
import pytest
from app.services import retention_queue as queue


class FakeRedis:
    def __init__(self):
        self.hashes = {}
        self.values = {}
        self.lists = {}
        self.zsets = {}
    async def hset(self, key, mapping):
        self.hashes.setdefault(key, {}).update({k: str(v) for k, v in mapping.items()})
    async def hgetall(self, key):
        return dict(self.hashes.get(key, {}))
    async def expire(self, *_args, **_kwargs):
        return True
    async def get(self, key):
        return self.values.get(key)
    async def set(self, key, value, *, ex=None, nx=False):
        if nx and (key in self.values or key in self.hashes):
            return None
        self.values[key] = str(value)
        return True
    async def delete(self, *keys):
        count = 0
        for key in keys:
            for store in (self.values, self.hashes, self.lists, self.zsets):
                if key in store:
                    del store[key]
                    count += 1
        return count
    async def rpush(self, key, *values):
        self.lists.setdefault(key, []).extend(str(v) for v in values)
        return len(self.lists[key])
    async def zadd(self, key, mapping):
        self.zsets.setdefault(key, {}).update({k: float(v) for k, v in mapping.items()})
    async def zrangebyscore(self, key, *, min, max, start=0, num=None):
        pairs = sorted((m, s) for m, s in self.zsets.get(key, {}).items() if float(min) <= s <= float(max))
        members = [m for m, _ in pairs][start:]
        return members if num is None else members[:num]
    async def zrem(self, key, *members):
        values = self.zsets.setdefault(key, {})
        removed = 0
        for member in members:
            if member in values:
                del values[member]
                removed += 1
        return removed
    async def lrange(self, key, start, end):
        values = self.lists.get(key, [])
        return values[start:] if end == -1 else values[start:end + 1]
    async def aclose(self):
        return None


def _job_mapping(*, tenant_id="tenant-a", attempt=0, max_attempts=3):
    now = time.time()
    return {"tenant_id": tenant_id, "tenant_slug": tenant_id,
        "payload": json.dumps({"risk_levels": ["critico"], "dry_run": True}),
        "status": "queued", "attempt": str(attempt), "max_attempts": str(max_attempts),
        "created_at": str(now), "updated_at": str(now)}


class FakeSessionContext:
    async def __aenter__(self):
        return object()
    async def __aexit__(self, *_args):
        return None


@pytest.mark.asyncio
async def test_enqueue_idempotency_is_tenant_scoped_and_emits_events(monkeypatch, caplog):
    redis = FakeRedis()
    settings = queue.get_settings()
    monkeypatch.setattr(queue, "redis_client", lambda: redis)
    caplog.set_level(logging.INFO, logger="app.services.retention_queue")
    first = await queue.enqueue_retention_job(tenant_id="tenant-a", tenant_slug="a", payload={"dry_run": True}, idempotency_key="same-request")
    repeated = await queue.enqueue_retention_job(tenant_id="tenant-a", tenant_slug="a", payload={"dry_run": True}, idempotency_key="same-request")
    other = await queue.enqueue_retention_job(tenant_id="tenant-b", tenant_slug="b", payload={"dry_run": True}, idempotency_key="same-request")
    assert repeated["id"] == first["id"] and repeated["deduplicated"] is True
    assert other["id"] != first["id"]
    assert len(redis.lists[settings.retention_queue_name]) == 2
    names = [r.event_name for r in caplog.records]
    assert "retention_job_enqueued" in names and "retention_job_deduplicated" in names


@pytest.mark.asyncio
async def test_failed_job_is_scheduled_for_exponential_retry(monkeypatch, caplog):
    redis = FakeRedis()
    settings = queue.get_settings()
    settings.retention_retry_backoff_seconds = 3
    job_id = "retry-test"
    await redis.hset(queue._job_key(job_id), mapping=_job_mapping())
    from app.agents import orchestrator as orch_module
    import app.db.session as db_module
    class FailingOrchestrator:
        def __init__(self, *_args, **_kwargs): pass
        async def run(self, **_kwargs): raise TimeoutError("synthetic provider timeout")
    monkeypatch.setattr(orch_module, "RetentionOrchestrator", FailingOrchestrator)
    monkeypatch.setattr(db_module, "AsyncSessionLocal", lambda: FakeSessionContext())
    caplog.set_level(logging.INFO, logger="app.services.retention_queue")
    completed = await queue.process_retention_job(job_id, redis)
    job = await queue.get_job(job_id, redis=redis)
    delayed = f"{settings.retention_queue_name}{queue.DELAYED_SUFFIX}"
    assert completed is False and job["status"] == "retrying" and job["attempt"] == 1
    assert job["last_error"] == "synthetic provider timeout"
    assert 2.5 <= job["next_retry_at"] - time.time() <= 3.5
    assert redis.zsets[delayed][job_id] == job["next_retry_at"]
    event = next(r for r in caplog.records if r.event_name == "retention_job_retry_scheduled")
    assert event.error_type == "TimeoutError"
    assert not hasattr(event, "payload")


@pytest.mark.asyncio
async def test_exhausted_job_moves_to_dead_letter_queue(monkeypatch, caplog):
    redis = FakeRedis()
    settings = queue.get_settings()
    job_id = "dead-letter-test"
    await redis.hset(queue._job_key(job_id), mapping=_job_mapping(attempt=1, max_attempts=2))
    from app.agents import orchestrator as orch_module
    import app.db.session as db_module
    class FailingOrchestrator:
        def __init__(self, *_args, **_kwargs): pass
        async def run(self, **_kwargs): raise RuntimeError("synthetic persistent failure")
    monkeypatch.setattr(orch_module, "RetentionOrchestrator", FailingOrchestrator)
    monkeypatch.setattr(db_module, "AsyncSessionLocal", lambda: FakeSessionContext())
    caplog.set_level(logging.INFO, logger="app.services.retention_queue")
    completed = await queue.process_retention_job(job_id, redis)
    job = await queue.get_job(job_id, redis=redis)
    assert completed is True and job["status"] == "dead_letter" and job["attempt"] == 2
    assert redis.lists[settings.retention_dead_letter_queue_name] == [job_id]
    event = next(r for r in caplog.records if r.event_name == "retention_job_dead_lettered")
    assert event.error_type == "RuntimeError" and event.attempt == 2 and event.max_attempts == 2


@pytest.mark.asyncio
async def test_only_due_retries_are_promoted_to_the_ready_queue(monkeypatch, caplog):
    redis = FakeRedis()
    settings = queue.get_settings()
    delayed = f"{settings.retention_queue_name}{queue.DELAYED_SUFFIX}"
    await redis.zadd(delayed, {"due-job": time.time() - 30, "future-job": time.time() + 600})
    caplog.set_level(logging.INFO, logger="app.services.retention_queue")
    moved = await queue.promote_due_retries(redis)
    assert moved == 1 and redis.lists[settings.retention_queue_name] == ["due-job"]
    assert set(redis.zsets[delayed]) == {"future-job"}
    event = next(r for r in caplog.records if r.event_name == "retention_job_retries_promoted")
    assert event.count == 1


@pytest.mark.asyncio
async def test_job_status_lookup_never_returns_another_tenants_job():
    redis = FakeRedis()
    await redis.hset(queue._job_key("tenant-boundary"), mapping=_job_mapping(tenant_id="tenant-a"))
    assert (await queue.get_job("tenant-boundary", tenant_id="tenant-a", redis=redis))["tenant_id"] == "tenant-a"
    assert await queue.get_job("tenant-boundary", tenant_id="tenant-b", redis=redis) is None
