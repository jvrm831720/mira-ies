"""Durable SophiA read-only synchronization worker.

Run with: python -m app.services.connectors.sophia_sync_worker [--once]
Only explicitly allowlisted tenant UUIDs are eligible for execution.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import socket
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert

from app.db.session import AsyncSessionLocal, engine
from app.models.sophia_connection import TenantSophiaConnection, TenantSophiaStudentLink
from app.models.sophia_sync import SophiaSyncJob, SophiaSyncJobEvent, SophiaStudentResource
from app.services.connectors.sophia_api import SophiaApiClient, SophiaApiConfig
from app.services.connectors.sophia_secrets import decrypt_sophia_secret\nfrom app.services.connectors.sophia_normalization import normalize_sophia_resource


RESOURCES = {
    "finance": "get_student_finance",
    "report_card": "get_student_report_card",
    "recent_grades": "get_student_recent_grades",
}
RETRYABLE = (TimeoutError, ConnectionError, OSError)


def _tenant_allowlist() -> tuple[str, ...]:
    values = tuple(x.strip() for x in os.getenv("SOPHIA_SYNC_WORKER_TENANT_IDS", "").split(",") if x.strip())
    if not values:
        raise RuntimeError("SOPHIA_SYNC_WORKER_TENANT_IDS must contain explicit tenant UUIDs.")
    return values


class SophiaSyncWorker:
    def __init__(self, *, worker_id: str, tenant_ids: tuple[str, ...]):
        if not tenant_ids:
            raise ValueError("At least one authorized tenant is required.")
        self.worker_id = worker_id
        self.tenant_ids = tenant_ids

    @staticmethod
    async def _tenant(session, tenant_id: str) -> None:
        await session.execute(text("SELECT set_config('app.tenant_id', :tenant_id, true)"), {"tenant_id": tenant_id})

    async def claim(self, tenant_id: str):
        async with AsyncSessionLocal() as session, session.begin():
            await self._tenant(session, tenant_id)
            now = datetime.now(timezone.utc)
            # Recover only abandoned leases; a running worker must heartbeat within 3 minutes.
            stale = (await session.execute(select(SophiaSyncJob).where(
                SophiaSyncJob.tenant_id == tenant_id,
                SophiaSyncJob.status == "running",
                SophiaSyncJob.heartbeat_at < now - timedelta(minutes=3),
            ).with_for_update(skip_locked=True))).scalars().all()
            for row in stale:
                row.status = "retry_wait" if row.attempts < row.max_attempts else "failed"
                row.available_at = now + timedelta(seconds=min(300, 15 * (2 ** max(0, row.attempts - 1))))
                row.worker_id = None
                row.locked_at = None
                row.heartbeat_at = None
                row.error_code = "worker_lease_expired"
                row.error_message = "Worker lease expired; execution recovered safely."
                if row.status == "failed":
                    row.finished_at = now
                session.add(SophiaSyncJobEvent(
                    tenant_id=tenant_id, job_id=row.id, event_type="lease_recovered",
                    details={"next_status": row.status},
                ))
            row = (await session.execute(select(SophiaSyncJob).where(
                SophiaSyncJob.tenant_id == tenant_id,
                SophiaSyncJob.status.in_(("queued", "retry_wait")),
                SophiaSyncJob.available_at <= now,
            ).order_by(SophiaSyncJob.created_at).limit(1).with_for_update(skip_locked=True))).scalar_one_or_none()
            if row is None:
                return None
            row.status = "running"
            row.attempts += 1
            row.worker_id = self.worker_id
            row.locked_at = now
            row.heartbeat_at = now
            row.started_at = row.started_at or now
            session.add(SophiaSyncJobEvent(
                tenant_id=tenant_id, job_id=row.id, event_type="started",
                details={"attempt": row.attempts, "worker_id": self.worker_id},
            ))
            return {"id": row.id, "tenant_id": tenant_id, "request": dict(row.request or {}),
                    "attempts": row.attempts, "max_attempts": row.max_attempts}

    async def heartbeat(self, job_id: str, tenant_id: str) -> bool:
        async with AsyncSessionLocal() as session, session.begin():
            await self._tenant(session, tenant_id)
            result = await session.execute(
                SophiaSyncJob.__table__.update().where(
                    SophiaSyncJob.id == job_id, SophiaSyncJob.tenant_id == tenant_id,
                    SophiaSyncJob.worker_id == self.worker_id, SophiaSyncJob.status == "running",
                ).values(heartbeat_at=datetime.now(timezone.utc))
            )
            return bool(result.rowcount)

    async def _execute(self, job: dict) -> dict:
        tenant_id = job["tenant_id"]
        async with AsyncSessionLocal() as session, session.begin():
            await self._tenant(session, tenant_id)
            connection = (await session.execute(select(TenantSophiaConnection).where(
                TenantSophiaConnection.tenant_id == tenant_id,
                TenantSophiaConnection.is_enabled.is_(True),
            ))).scalar_one_or_none()
            if connection is None:
                raise ValueError("sophia_connection_not_enabled")
            links_query = select(TenantSophiaStudentLink)
            student_ids = job["request"].get("student_ids") or []
            links_query = links_query.where(TenantSophiaStudentLink.tenant_id == tenant_id)
            if student_ids:
                links_query = links_query.where(TenantSophiaStudentLink.student_id.in_(student_ids))
            links = (await session.execute(links_query.order_by(TenantSophiaStudentLink.student_id))).scalars().all()
            if not links:
                raise ValueError("no_linked_students")
            config = SophiaApiConfig(
                base_url=connection.base_url,
                username=decrypt_sophia_secret(connection.encrypted_username),
                password=decrypt_sophia_secret(connection.encrypted_password),
            )
            link_data = [(link.student_id, link.codigo_interno) for link in links]

        client = SophiaApiClient(config)
        completed = 0
        resource_counts: dict[str, int] = {}
        try:
            for student_id, codigo in link_data:
                if not await self.heartbeat(job["id"], tenant_id):
                    raise RuntimeError("worker_lease_lost")
                for resource, method_name in RESOURCES.items():
                    method = getattr(client, method_name)
                    payload = await method(codigo)
                    if not isinstance(payload, list):
                        raise ValueError(f"invalid_{resource}_payload")
                    async with AsyncSessionLocal() as session, session.begin():
                        await self._tenant(session, tenant_id)
                        values = {
                            "id": str(uuid4()), "tenant_id": tenant_id, "student_id": student_id,
                            "job_id": job["id"], "resource": resource,
                            "source_codigo_interno": codigo, "payload": normalize_sophia_resource(resource, payload),
                            "record_count": len(payload),
                            "observed_at": datetime.now(timezone.utc),
                            "updated_at": datetime.now(timezone.utc),
                        }
                        stmt = insert(SophiaStudentResource).values(**values)
                        stmt = stmt.on_conflict_do_update(
                            constraint="uq_sophia_resource_student",
                            set_={k: stmt.excluded[k] for k in (
                                "job_id", "source_codigo_interno", "payload", "record_count", "observed_at", "updated_at"
                            )},
                        )
                        await session.execute(stmt)
                    resource_counts[resource] = resource_counts.get(resource, 0) + len(payload)
                completed += 1
        finally:
            await client.close()
        return {"students_completed": completed, "resource_record_counts": resource_counts}

    async def run_once(self) -> bool:
        for tenant_id in self.tenant_ids:
            job = await self.claim(tenant_id)
            if job is None:
                continue
            try:
                result = await self._execute(job)
                async with AsyncSessionLocal() as session, session.begin():
                    await self._tenant(session, tenant_id)
                    row = (await session.execute(select(SophiaSyncJob).where(
                        SophiaSyncJob.id == job["id"], SophiaSyncJob.tenant_id == tenant_id,
                        SophiaSyncJob.worker_id == self.worker_id, SophiaSyncJob.status == "running",
                    ).with_for_update())).scalar_one_or_none()
                    if row is None:
                        raise RuntimeError("worker_lease_lost_before_finish")
                    row.status = "succeeded"
                    row.finished_at = datetime.now(timezone.utc)
                    row.worker_id = None
                    row.locked_at = None
                    row.heartbeat_at = None
                    row.error_code = None
                    row.error_message = None
                    session.add(SophiaSyncJobEvent(
                        tenant_id=tenant_id, job_id=job["id"], event_type="succeeded", details=result,
                    ))
            except Exception as exc:
                async with AsyncSessionLocal() as session, session.begin():
                    await self._tenant(session, tenant_id)
                    row = (await session.execute(select(SophiaSyncJob).where(
                        SophiaSyncJob.id == job["id"], SophiaSyncJob.tenant_id == tenant_id,
                        SophiaSyncJob.worker_id == self.worker_id,
                    ).with_for_update())).scalar_one_or_none()
                    if row is not None:
                        retry = row.attempts < row.max_attempts
                        row.status = "retry_wait" if retry else "failed"
                        row.available_at = datetime.now(timezone.utc) + timedelta(
                            seconds=min(900, 30 * (2 ** max(0, row.attempts - 1)))
                        )
                        row.finished_at = None if retry else datetime.now(timezone.utc)
                        row.worker_id = None
                        row.locked_at = None
                        row.heartbeat_at = None
                        row.error_code = type(exc).__name__[:80]
                        row.error_message = "Falha na sincronização SophiA. Consulte os eventos; detalhes sensíveis da origem não são persistidos."
                        session.add(SophiaSyncJobEvent(
                            tenant_id=tenant_id, job_id=job["id"], event_type="retry_scheduled" if retry else "failed",
                            details={"error_type": type(exc).__name__, "attempt": row.attempts},
                        ))
            return True
        return False

    async def serve(self, *, once: bool = False, poll_seconds: float = 2.0) -> None:
        while True:
            processed = await self.run_once()
            if once:
                return
            if not processed:
                await asyncio.sleep(max(0.5, poll_seconds))


async def _main(once: bool) -> None:
    worker = SophiaSyncWorker(
        worker_id=f"sophia-{socket.gethostname()}-{os.getpid()}",
        tenant_ids=_tenant_allowlist(),
    )
    try:
        await worker.serve(once=once)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    asyncio.run(_main(args.once))
