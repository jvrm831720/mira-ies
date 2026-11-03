"""Unit and PostgreSQL integration tests for the durable RM sync orchestrator."""
from __future__ import annotations

from uuid import uuid4

import pytest

from app.db.session import AsyncSessionLocal
from app.models.rm_sync import RmSyncScope
from app.services.connectors.totvs_rm_sync_orchestrator import (
    RMJobCancelled,
    RMJobConflict,
    RMPostgresSyncQueue,
    RMTransientJobError,
    RMSyncWorker,
    classify_job_error,
    retry_delay_seconds,
)


def test_retry_backoff_is_exponential_and_capped():
    assert retry_delay_seconds(1) == 15
    assert retry_delay_seconds(2) == 30
    assert retry_delay_seconds(3) == 60
    assert retry_delay_seconds(20) == 1800
    with pytest.raises(ValueError):
        retry_delay_seconds(0)


def test_error_classification_fails_closed():
    assert classify_job_error(TimeoutError())[1] is True
    assert classify_job_error(RMTransientJobError("temporary")) == ("transient_error", True)
    assert classify_job_error(ValueError("mapping"))[1] is False


@pytest.mark.asyncio
async def test_queue_idempotency_concurrency_cancel_and_tenant_metrics(db_session, tenant):
    tenant_row, _ = tenant
    tenant_id = str(tenant_row.id)
    scope_id = str(uuid4())
    await db_session.rollback()
    await db_session.execute(
        __import__("sqlalchemy").text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": tenant_id},
    )
    db_session.add(RmSyncScope(
        id=scope_id, tenant_id=tenant_id, coligada_id="001",
        source_name="EduParcelaData", entity_name="installments", schema_version="v1",
    ))
    await db_session.commit()

    queue = RMPostgresSyncQueue(AsyncSessionLocal)
    key = f"test-{uuid4()}"
    job_id = await queue.enqueue(
        tenant_id=tenant_id, scope_id=scope_id, idempotency_key=key,
        request={"mode": "full_snapshot"},
    )
    assert await queue.enqueue(
        tenant_id=tenant_id, scope_id=scope_id, idempotency_key=key,
        request={"mode": "full_snapshot"},
    ) == job_id

    other_scope_id = await queue.ensure_scope(
        tenant_id=tenant_id, coligada_id="001", source_name="EduAlunoData",
        entity_name="students", schema_version="v1",
    )
    with pytest.raises(RMJobConflict, match="coligada"):
        await queue.enqueue(
            tenant_id=tenant_id, scope_id=other_scope_id, idempotency_key=f"other-{uuid4()}",
            request={"mode": "full_snapshot"},
        )

    status = await queue.request_cancel(tenant_id=tenant_id, job_id=job_id)
    assert status == "cancelled"
    history = await queue.history(tenant_id=tenant_id, scope_id=scope_id)
    assert history[0]["status"] == "cancelled"
    events = await queue.events(tenant_id=tenant_id, job_id=job_id)
    assert [event["event_type"] for event in events] == ["queued", "cancelled"]
    metrics = await queue.metrics(tenant_id=tenant_id)
    assert metrics["jobs_by_status"]["cancelled"] >= 1
    assert await queue.claim(tenant_id=str(uuid4()), worker_id="wrong-tenant") is None


@pytest.mark.asyncio
async def test_worker_executes_and_completes_job(db_session, tenant):
    tenant_row, _ = tenant
    tenant_id = str(tenant_row.id)
    scope_id = str(uuid4())
    await db_session.rollback()
    from sqlalchemy import text
    await db_session.execute(text("SELECT set_config('app.tenant_id', :tenant_id, true)"), {"tenant_id": tenant_id})
    db_session.add(RmSyncScope(
        id=scope_id, tenant_id=tenant_id, coligada_id="002",
        source_name="EduParcelaData", entity_name="installments", schema_version="v1",
    ))
    await db_session.commit()

    queue = RMPostgresSyncQueue(AsyncSessionLocal)
    job_id = await queue.enqueue(
        tenant_id=tenant_id, scope_id=scope_id, idempotency_key=f"worker-{uuid4()}",
        request={"mode": "full_snapshot"},
    )
    calls = []

    async def executor(job, heartbeat, cancelled, attach_snapshot):
        calls.append(job["id"])
        assert await heartbeat() is True
        assert await cancelled() is False
        return {"snapshot_run_id": None}

    worker = RMSyncWorker(
        queue, executor, worker_id="pytest-worker", tenant_ids=(tenant_id,)
    )
    assert await worker.run_once() is True
    assert calls == [job_id]
    assert (await queue.history(tenant_id=tenant_id, scope_id=scope_id))[0]["status"] == "succeeded"


@pytest.mark.asyncio
async def test_transient_failure_is_scheduled_for_retry(db_session, tenant):
    tenant_row, _ = tenant
    tenant_id = str(tenant_row.id)
    scope_id = str(uuid4())
    await db_session.rollback()
    from sqlalchemy import text
    await db_session.execute(text("SELECT set_config('app.tenant_id', :tenant_id, true)"), {"tenant_id": tenant_id})
    db_session.add(RmSyncScope(
        id=scope_id, tenant_id=tenant_id, coligada_id="003",
        source_name="EduParcelaData", entity_name="installments", schema_version="v1",
    ))
    await db_session.commit()

    queue = RMPostgresSyncQueue(AsyncSessionLocal)
    await queue.enqueue(
        tenant_id=tenant_id, scope_id=scope_id, idempotency_key=f"retry-{uuid4()}",
        request={"mode": "full_snapshot"}, max_attempts=3,
    )
    job = await queue.claim(tenant_id=tenant_id, worker_id="retry-worker")
    assert job is not None
    status = await queue.fail(
        tenant_id=tenant_id, job_id=job["id"], worker_id="retry-worker",
        exc=RMTransientJobError("upstream timeout"),
        attempt=job["attempt"], max_attempts=job["max_attempts"],
    )
    assert status == "retry_wait"
    history = await queue.history(tenant_id=tenant_id, scope_id=scope_id)
    assert history[0]["status"] == "retry_wait"
    assert history[0]["error_code"] == "transient_error"



@pytest.mark.asyncio
async def test_scope_can_be_created_before_first_snapshot_and_credentials_are_rejected(tenant):
    tenant_row, _ = tenant
    tenant_id = str(tenant_row.id)
    queue = RMPostgresSyncQueue(AsyncSessionLocal)
    scope_id = await queue.ensure_scope(
        tenant_id=tenant_id, coligada_id="004", source_name="EduParcelaData",
        entity_name="installments", schema_version="v1",
    )
    assert await queue.ensure_scope(
        tenant_id=tenant_id, coligada_id="004", source_name="EduParcelaData",
        entity_name="installments", schema_version="v1",
    ) == scope_id
    with pytest.raises(ValueError, match="credenciais"):
        await queue.enqueue(
            tenant_id=tenant_id, scope_id=scope_id,
            idempotency_key=f"secret-{uuid4()}",
            request={"connector": {"access_token": "must-not-persist"}},
        )


@pytest.mark.asyncio
async def test_expired_worker_lease_is_recovered_and_fenced(db_session, tenant):
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import text, update
    from app.models.rm_sync_jobs import RmSyncJob

    tenant_row, _ = tenant
    tenant_id = str(tenant_row.id)
    scope_id = str(uuid4())
    await db_session.rollback()
    await db_session.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": tenant_id},
    )
    db_session.add(RmSyncScope(
        id=scope_id, tenant_id=tenant_id, coligada_id="005",
        source_name="EduParcelaData", entity_name="installments", schema_version="v1",
    ))
    await db_session.commit()

    queue = RMPostgresSyncQueue(AsyncSessionLocal)
    await queue.enqueue(
        tenant_id=tenant_id, scope_id=scope_id,
        idempotency_key=f"lease-{uuid4()}", request={"mode": "full_snapshot"},
    )
    first = await queue.claim(tenant_id=tenant_id, worker_id="worker-old")
    assert first is not None
    async with AsyncSessionLocal() as session, session.begin():
        await session.execute(
            text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
            {"tenant_id": tenant_id},
        )
        await session.execute(update(RmSyncJob).where(
            RmSyncJob.id == first["id"], RmSyncJob.tenant_id == tenant_id
        ).values(heartbeat_at=datetime.now(timezone.utc) - timedelta(hours=1)))

    recovered = await queue.claim(tenant_id=tenant_id, worker_id="worker-new", lease_seconds=30)
    assert recovered is not None
    assert recovered["id"] == first["id"]
    assert recovered["attempt"] == 2
    assert await queue.heartbeat(
        tenant_id=tenant_id, job_id=first["id"], worker_id="worker-old"
    ) is False
    assert await queue.heartbeat(
        tenant_id=tenant_id, job_id=first["id"], worker_id="worker-new"
    ) is True



@pytest.mark.asyncio
async def test_running_job_cancels_cooperatively_before_publication(db_session, tenant):
    tenant_row, _ = tenant
    tenant_id = str(tenant_row.id)
    scope_id = str(uuid4())
    await db_session.rollback()
    from sqlalchemy import text
    await db_session.execute(text("SELECT set_config('app.tenant_id', :tenant_id, true)"), {"tenant_id": tenant_id})
    db_session.add(RmSyncScope(
        id=scope_id, tenant_id=tenant_id, coligada_id="006",
        source_name="EduParcelaData", entity_name="installments", schema_version="v1",
    ))
    await db_session.commit()

    queue = RMPostgresSyncQueue(AsyncSessionLocal)
    job_id = await queue.enqueue(
        tenant_id=tenant_id, scope_id=scope_id,
        idempotency_key=f"cancel-running-{uuid4()}", request={"mode": "full_snapshot"},
    )

    async def executor(job, heartbeat, cancelled, attach_snapshot):
        assert await heartbeat() is True
        assert await queue.request_cancel(tenant_id=tenant_id, job_id=job_id) == "cancel_requested"
        assert await cancelled() is True
        raise RMJobCancelled()

    worker = RMSyncWorker(
        queue, executor, worker_id="cancel-worker", tenant_ids=(tenant_id,)
    )
    assert await worker.run_once() is True
    assert (await queue.history(tenant_id=tenant_id, scope_id=scope_id))[0]["status"] == "cancelled"
