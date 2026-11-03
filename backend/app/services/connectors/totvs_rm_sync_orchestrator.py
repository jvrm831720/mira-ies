"""Durable queue, lease management and execution policy for TOTVS RM sync jobs.

The source adapter is injected by the worker. Credentials must be resolved by that
adapter from the institution's approved secret store; they are never queue payload.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable
from uuid import uuid4

import httpx

from sqlalchemy import extract, func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.rm_sync import RmSyncRun, RmSyncScope
from app.models.rm_sync_jobs import RmSyncJob, RmSyncJobEvent


ACTIVE_STATUSES = ("queued", "running", "retry_wait", "cancel_requested")
TERMINAL_STATUSES = ("cancelled", "succeeded", "failed")


class RMJobError(RuntimeError):
    code = "permanent_error"
    retryable = False


class RMTransientJobError(RMJobError):
    code = "transient_error"
    retryable = True


class RMJobCancelled(Exception):
    """Cooperative cancellation requested by an operator."""


class RMJobConflict(RuntimeError):
    pass


class RMJobNotFound(RMJobConflict):
    """Job does not exist in the authenticated tenant."""


def retry_delay_seconds(attempt: int, *, base: int = 15, cap: int = 1800) -> int:
    """Capped exponential backoff; attempt is 1-based."""
    if attempt < 1:
        raise ValueError("attempt deve ser >= 1")
    return min(cap, base * (2 ** (attempt - 1)))


def classify_job_error(exc: BaseException) -> tuple[str, bool]:
    if isinstance(exc, RMJobError):
        return exc.code, exc.retryable
    if isinstance(exc, (TimeoutError, asyncio.TimeoutError, ConnectionError, OSError, httpx.TimeoutException, httpx.TransportError)):
        return "transport_unavailable", True
    # Validation, auth, mapping and unknown application errors fail closed.
    return "execution_failed", False


def _safe_request(value: Any, path: str = "request") -> None:
    forbidden = {"password", "token", "access_token", "refresh_token", "api_key", "apikey", "client_secret", "private_key", "secret", "authorization", "credential", "bearer", "auth"}
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in forbidden:
                raise ValueError(f"{path} não pode armazenar credenciais.")
            _safe_request(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _safe_request(child, f"{path}[{index}]")


class RMPostgresSyncQueue:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]):
        self.sessions = sessions

    @staticmethod
    async def _tenant(session: AsyncSession, tenant_id: str) -> None:
        await session.execute(
            text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
            {"tenant_id": tenant_id},
        )

    @staticmethod
    def _event(session: AsyncSession, *, tenant_id: str, job_id: str,
               event_type: str, severity: str = "info", details: dict | None = None) -> None:
        session.add(RmSyncJobEvent(
            tenant_id=tenant_id, job_id=job_id, event_type=event_type,
            severity=severity, details=details or {},
        ))

    async def ensure_scope(
        self, *, tenant_id: str, coligada_id: str, source_name: str,
        entity_name: str, schema_version: str,
    ) -> str:
        """Create or return the stable tenant/coligada/source scope before first sync."""
        async with self.sessions() as session, session.begin():
            await self._tenant(session, tenant_id)
            await session.execute(
                pg_insert(RmSyncScope).values(
                    id=str(uuid4()), tenant_id=tenant_id, coligada_id=coligada_id,
                    source_name=source_name, entity_name=entity_name,
                    schema_version=schema_version,
                ).on_conflict_do_nothing(index_elements=[
                    "tenant_id", "coligada_id", "source_name", "entity_name", "schema_version"
                ])
            )
            scope = (await session.execute(select(RmSyncScope).where(
                RmSyncScope.tenant_id == tenant_id,
                RmSyncScope.coligada_id == coligada_id,
                RmSyncScope.source_name == source_name,
                RmSyncScope.entity_name == entity_name,
                RmSyncScope.schema_version == schema_version,
            ))).scalar_one()
            return scope.id

    async def enqueue(
        self, *, tenant_id: str, scope_id: str, idempotency_key: str,
        request: dict | None = None, max_attempts: int = 5,
        actor_user_id: str | None = None, actor_type: str = "system",
    ) -> str:
        if not idempotency_key or not idempotency_key.strip() or len(idempotency_key) > 160:
            raise ValueError("idempotency_key deve conter de 1 a 160 caracteres.")
        if not 1 <= max_attempts <= 12:
            raise ValueError("max_attempts deve estar entre 1 e 12.")
        payload = {} if request is None else request
        if not isinstance(payload, dict):
            raise ValueError("request deve ser um objeto JSON.")
        _safe_request(payload)
        async with self.sessions() as session, session.begin():
            await self._tenant(session, tenant_id)
            scope = (await session.execute(
                select(RmSyncScope).where(
                    RmSyncScope.id == scope_id, RmSyncScope.tenant_id == tenant_id
                ).with_for_update()
            )).scalar_one_or_none()
            if scope is None:
                raise RMJobConflict("Escopo não encontrado neste tenant.")
            await session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
                {"lock_key": f"idempotency:{tenant_id}:{idempotency_key}"},
            )
            existing_key = (await session.execute(
                select(RmSyncJob).where(
                    RmSyncJob.tenant_id == tenant_id,
                    RmSyncJob.idempotency_key == idempotency_key,
                )
            )).scalar_one_or_none()
            if existing_key:
                if (
                    existing_key.scope_id == scope_id
                    and existing_key.request == payload
                    and existing_key.max_attempts == max_attempts
                ):
                    return existing_key.id
                raise RMJobConflict("Chave de idempotência já usada com outro conteúdo.")
            await session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
                {"lock_key": f"{tenant_id}:{scope.coligada_id}"},
            )
            active = (await session.execute(
                select(RmSyncJob).where(
                    RmSyncJob.coligada_id == scope.coligada_id,
                    RmSyncJob.tenant_id == tenant_id,
                    RmSyncJob.status.in_(ACTIVE_STATUSES),
                ).with_for_update()
            )).scalar_one_or_none()
            if active:
                raise RMJobConflict("Já existe uma sincronização ativa para esta coligada.")
            job_id = str(uuid4())
            session.add(RmSyncJob(
                id=job_id, tenant_id=tenant_id, scope_id=scope_id,
                coligada_id=scope.coligada_id,
                idempotency_key=idempotency_key, request=payload,
                status="queued", max_attempts=max_attempts,
            ))
            self._event(session, tenant_id=tenant_id, job_id=job_id,
                        event_type="queued", details={"scope_id": scope_id, "actor_user_id": actor_user_id, "actor_type": actor_type})
            return job_id

    async def claim(self, *, tenant_id: str, worker_id: str, lease_seconds: int = 120) -> dict | None:
        now = datetime.now(timezone.utc)
        stale_before = now - timedelta(seconds=lease_seconds)
        async with self.sessions() as session, session.begin():
            # Each claim is scoped to one tenant. The worker never bypasses RLS.
            await self._tenant(session, tenant_id)
            candidate = (await session.execute(
                select(RmSyncJob).where(
                    RmSyncJob.tenant_id == tenant_id,
                    (
                        (RmSyncJob.status.in_(("queued", "retry_wait"))
                         & (RmSyncJob.available_at <= now))
                        | ((RmSyncJob.status == "running")
                           & (RmSyncJob.heartbeat_at < stale_before))
                    )
                ).order_by(RmSyncJob.available_at, RmSyncJob.created_at)
                .with_for_update(skip_locked=True).limit(1)
            )).scalar_one_or_none()
            if candidate is None:
                return None
            if candidate.attempts >= candidate.max_attempts:
                candidate.status = "failed"
                candidate.finished_at = now
                candidate.error_code = "worker_lease_exhausted"
                candidate.error_message = "Limite de tentativas atingido após perda de lease."
                self._event(session, tenant_id=candidate.tenant_id, job_id=candidate.id,
                            event_type="failed", severity="error",
                            details={"code": candidate.error_code})
                return None
            reclaimed = candidate.status == "running"
            candidate.status = "running"
            candidate.attempts += 1
            candidate.worker_id = worker_id
            candidate.locked_at = now
            candidate.heartbeat_at = now
            candidate.started_at = candidate.started_at or now
            self._event(session, tenant_id=candidate.tenant_id, job_id=candidate.id,
                        event_type="lease_recovered" if reclaimed else "started",
                        details={"attempt": candidate.attempts, "worker_id": worker_id})
            return {
                "id": candidate.id, "tenant_id": candidate.tenant_id,
                "scope_id": candidate.scope_id, "snapshot_run_id": candidate.snapshot_run_id,
                "request": candidate.request, "attempt": candidate.attempts,
                "max_attempts": candidate.max_attempts,
            }

    async def attach_snapshot_run(self, *, tenant_id: str, job_id: str, worker_id: str, snapshot_run_id: str) -> None:
        async with self.sessions() as session, session.begin():
            await self._tenant(session, tenant_id)
            row = (await session.execute(select(RmSyncJob).where(
                RmSyncJob.id == job_id, RmSyncJob.tenant_id == tenant_id
            ).with_for_update())).scalar_one_or_none()
            if row is None or row.worker_id != worker_id or row.status != "running":
                raise RMJobConflict("Lease inválido ao associar snapshot ao job.")
            run_scope_id = (await session.execute(select(RmSyncRun.scope_id).where(
                RmSyncRun.id == snapshot_run_id, RmSyncRun.tenant_id == tenant_id
            ))).scalar_one_or_none()
            if run_scope_id != row.scope_id:
                raise RMJobConflict("O snapshot não pertence ao escopo/tenant deste job.")
            if row.snapshot_run_id and row.snapshot_run_id != snapshot_run_id:
                raise RMJobConflict("O job já está associado a outro snapshot.")
            row.snapshot_run_id = snapshot_run_id
            self._event(session, tenant_id=tenant_id, job_id=job_id,
                        event_type="snapshot_attached", details={"snapshot_run_id": snapshot_run_id})

    async def heartbeat(self, *, tenant_id: str, job_id: str, worker_id: str) -> bool:
        async with self.sessions() as session, session.begin():
            await self._tenant(session, tenant_id)
            row = (await session.execute(
                select(RmSyncJob).where(
                    RmSyncJob.id == job_id, RmSyncJob.tenant_id == tenant_id
                ).with_for_update()
            )).scalar_one_or_none()
            if row is None or row.worker_id != worker_id:
                return False
            if row.status == "cancel_requested":
                return False
            if row.status != "running":
                return False
            row.heartbeat_at = datetime.now(timezone.utc)
            return True

    async def cancellation_requested(self, *, tenant_id: str, job_id: str) -> bool:
        async with self.sessions() as session, session.begin():
            await self._tenant(session, tenant_id)
            row = (await session.execute(select(RmSyncJob.status).where(
                RmSyncJob.id == job_id, RmSyncJob.tenant_id == tenant_id
            ))).scalar_one_or_none()
            return row in ("cancel_requested", "cancelled")

    async def request_cancel(self, *, tenant_id: str, job_id: str, actor_user_id: str | None = None, actor_type: str = "system") -> str:
        async with self.sessions() as session, session.begin():
            await self._tenant(session, tenant_id)
            row = (await session.execute(select(RmSyncJob).where(
                RmSyncJob.id == job_id, RmSyncJob.tenant_id == tenant_id
            ).with_for_update())).scalar_one_or_none()
            if row is None:
                raise RMJobNotFound("Execução não encontrada.")
            if row.status in TERMINAL_STATUSES or row.status == "cancel_requested":
                return row.status
            now = datetime.now(timezone.utc)
            if row.status in ("queued", "retry_wait"):
                row.status = "cancelled"
                row.finished_at = now
            else:
                row.status = "cancel_requested"
                row.cancel_requested_at = now
            self._event(session, tenant_id=tenant_id, job_id=job_id,
                        event_type="cancelled" if row.status == "cancelled" else "cancel_requested",
                        details={"resulting_status": row.status, "actor_user_id": actor_user_id, "actor_type": actor_type})
            return row.status

    async def finish(self, *, tenant_id: str, job_id: str, worker_id: str,
                     snapshot_run_id: str | None = None) -> str:
        async with self.sessions() as session, session.begin():
            await self._tenant(session, tenant_id)
            row = (await session.execute(select(RmSyncJob).where(
                RmSyncJob.id == job_id, RmSyncJob.tenant_id == tenant_id
            ).with_for_update())).scalar_one_or_none()
            if row is None or row.worker_id != worker_id:
                raise RMJobConflict("Lease do worker não pertence a esta execução.")
            now = datetime.now(timezone.utc)
            effective_run_id = snapshot_run_id or row.snapshot_run_id
            if effective_run_id:
                run_scope_id = (await session.execute(select(RmSyncRun.scope_id).where(
                    RmSyncRun.id == effective_run_id, RmSyncRun.tenant_id == tenant_id
                ))).scalar_one_or_none()
                if run_scope_id != row.scope_id:
                    raise RMJobConflict("O snapshot final não pertence ao escopo/tenant deste job.")
            if row.status == "cancel_requested":
                row.status = "cancelled"
                row.finished_at = now
                event = "cancelled"
            else:
                row.status = "succeeded"
                row.snapshot_run_id = effective_run_id
                event = "succeeded"
            row.finished_at = now
            row.error_code = None if row.status == "succeeded" else row.error_code
            row.error_message = None if row.status == "succeeded" else row.error_message
            row.worker_id = None
            row.locked_at = None
            self._event(session, tenant_id=tenant_id, job_id=job_id, event_type=event)
            return row.status

    async def fail(self, *, tenant_id: str, job_id: str, worker_id: str,
                   exc: BaseException, attempt: int, max_attempts: int) -> str:
        code, retryable = classify_job_error(exc)
        now = datetime.now(timezone.utc)
        async with self.sessions() as session, session.begin():
            await self._tenant(session, tenant_id)
            row = (await session.execute(select(RmSyncJob).where(
                RmSyncJob.id == job_id, RmSyncJob.tenant_id == tenant_id
            ).with_for_update())).scalar_one_or_none()
            if row is None or row.worker_id != worker_id:
                raise RMJobConflict("Lease do worker não pertence a esta execução.")
            if row.status == "cancel_requested":
                row.status = "cancelled"
                row.finished_at = now
                event = "cancelled"
            elif retryable and attempt < max_attempts:
                delay = retry_delay_seconds(attempt)
                row.status = "retry_wait"
                row.available_at = now + timedelta(seconds=delay)
                row.error_code = code
                row.error_message = f"Falha de execução ({code}). Consulte o código e os eventos sem expor a resposta bruta da origem."
                event = "retry_scheduled"
            else:
                row.status = "failed"
                row.finished_at = now
                row.error_code = code
                row.error_message = f"Falha de execução ({code}). Consulte o código e os eventos sem expor a resposta bruta da origem."
                event = "failed"
            row.worker_id = None
            row.locked_at = None
            row.heartbeat_at = None
            self._event(session, tenant_id=tenant_id, job_id=job_id,
                        event_type=event, severity="warning" if event == "retry_scheduled" else "error",
                        details={"code": code, "attempt": attempt,
                                 "retryable": retryable,
                                 "available_at": row.available_at.isoformat() if event == "retry_scheduled" else None})
            return row.status

    @staticmethod
    def _serialize_job(job: RmSyncJob, scope: RmSyncScope) -> dict:
        return {
            "id": job.id,
            "scope_id": job.scope_id,
            "coligada_id": job.coligada_id,
            "source_name": scope.source_name,
            "entity_name": scope.entity_name,
            "schema_version": scope.schema_version,
            "snapshot_run_id": job.snapshot_run_id,
            "status": job.status,
            "attempts": job.attempts,
            "max_attempts": job.max_attempts,
            "available_at": job.available_at.isoformat() if job.available_at else None,
            "created_at": job.created_at.isoformat(),
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "finished_at": job.finished_at.isoformat() if job.finished_at else None,
            "error_code": job.error_code,
            "error_message": job.error_message,
            "request": {
                key: job.request.get(key)
                for key in ("mode", "page_size")
                if key in (job.request or {})
            },
        }

    async def scopes(self, *, tenant_id: str) -> list[dict]:
        async with self.sessions() as session, session.begin():
            await self._tenant(session, tenant_id)
            rows = (await session.execute(
                select(RmSyncScope).where(RmSyncScope.tenant_id == tenant_id)
                .order_by(RmSyncScope.coligada_id, RmSyncScope.source_name, RmSyncScope.entity_name)
            )).scalars().all()
            return [{
                "id": row.id, "coligada_id": row.coligada_id,
                "source_name": row.source_name, "entity_name": row.entity_name,
                "schema_version": row.schema_version,
                "current_snapshot_run_id": row.current_snapshot_run_id,
                "created_at": row.created_at.isoformat(),
                "updated_at": row.updated_at.isoformat(),
            } for row in rows]

    async def list_jobs(
        self, *, tenant_id: str, status: str | None = None,
        coligada_id: str | None = None, limit: int = 50, offset: int = 0,
    ) -> dict:
        async with self.sessions() as session, session.begin():
            await self._tenant(session, tenant_id)
            query = select(RmSyncJob, RmSyncScope).join(
                RmSyncScope,
                (RmSyncScope.id == RmSyncJob.scope_id)
                & (RmSyncScope.tenant_id == RmSyncJob.tenant_id),
            ).where(RmSyncJob.tenant_id == tenant_id)
            if status:
                query = query.where(RmSyncJob.status == status)
            if coligada_id:
                query = query.where(RmSyncJob.coligada_id == coligada_id)
            total = (await session.execute(
                select(func.count()).select_from(query.subquery())
            )).scalar_one()
            rows = (await session.execute(
                query.order_by(RmSyncJob.created_at.desc())
                .offset(offset).limit(limit)
            )).all()
            return {
                "total": total,
                "limit": limit,
                "offset": offset,
                "jobs": [self._serialize_job(job, scope) for job, scope in rows],
            }

    async def get_job(self, *, tenant_id: str, job_id: str) -> dict | None:
        async with self.sessions() as session, session.begin():
            await self._tenant(session, tenant_id)
            row = (await session.execute(
                select(RmSyncJob, RmSyncScope).join(
                    RmSyncScope,
                    (RmSyncScope.id == RmSyncJob.scope_id)
                    & (RmSyncScope.tenant_id == RmSyncJob.tenant_id),
                ).where(RmSyncJob.id == job_id, RmSyncJob.tenant_id == tenant_id)
            )).one_or_none()
            if row is None:
                return None
            return self._serialize_job(row[0], row[1])

    async def retry_failed(
        self, *, tenant_id: str, job_id: str, actor_user_id: str | None = None,
        max_manual_retries: int = 3, actor_type: str = "system",
    ) -> dict:
        async with self.sessions() as session, session.begin():
            await self._tenant(session, tenant_id)
            row = (await session.execute(
                select(RmSyncJob).where(
                    RmSyncJob.id == job_id, RmSyncJob.tenant_id == tenant_id
                ).with_for_update()
            )).scalar_one_or_none()
            if row is None:
                raise RMJobNotFound("Execução não encontrada.")
            if row.status != "failed":
                raise RMJobConflict("Somente execuções com falha podem receber nova tentativa manual.")
            await session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
                {"lock_key": f"{tenant_id}:{row.coligada_id}"},
            )
            active = (await session.execute(select(RmSyncJob.id).where(
                RmSyncJob.tenant_id == tenant_id,
                RmSyncJob.coligada_id == row.coligada_id,
                RmSyncJob.status.in_(ACTIVE_STATUSES),
                RmSyncJob.id != row.id,
            ).limit(1))).scalar_one_or_none()
            if active:
                raise RMJobConflict("Já existe uma sincronização ativa para esta coligada.")
            manual_retries = (await session.execute(
                select(func.count()).select_from(RmSyncJobEvent).where(
                    RmSyncJobEvent.tenant_id == tenant_id,
                    RmSyncJobEvent.job_id == job_id,
                    RmSyncJobEvent.event_type == "manual_retry",
                )
            )).scalar_one()
            if manual_retries >= max_manual_retries:
                raise RMJobConflict("Limite de novas tentativas manuais atingido.")
            previous_attempts = row.attempts
            row.status = "queued"
            row.attempts = 0
            row.available_at = datetime.now(timezone.utc)
            row.worker_id = None
            row.locked_at = None
            row.heartbeat_at = None
            row.cancel_requested_at = None
            row.started_at = None
            row.finished_at = None
            row.error_code = None
            row.error_message = None
            self._event(
                session, tenant_id=tenant_id, job_id=job_id,
                event_type="manual_retry", severity="warning",
                details={
                    "actor_user_id": actor_user_id,
                    "actor_type": actor_type,
                    "previous_attempts": previous_attempts,
                    "manual_retry_number": manual_retries + 1,
                },
            )
            return {"id": row.id, "status": row.status, "manual_retry_number": manual_retries + 1}

    async def history(self, *, tenant_id: str, scope_id: str, limit: int = 50) -> list[dict]:
        async with self.sessions() as session, session.begin():
            await self._tenant(session, tenant_id)
            rows = (await session.execute(select(RmSyncJob).where(
                RmSyncJob.tenant_id == tenant_id, RmSyncJob.scope_id == scope_id
            ).order_by(RmSyncJob.created_at.desc()).limit(max(1, min(limit, 200))))).scalars()
            return [{
                "id": r.id, "status": r.status, "attempts": r.attempts,
                "created_at": r.created_at.isoformat(), "started_at": r.started_at.isoformat() if r.started_at else None,
                "finished_at": r.finished_at.isoformat() if r.finished_at else None,
                "error_code": r.error_code,
            } for r in rows]

    async def events(self, *, tenant_id: str, job_id: str, limit: int = 100) -> list[dict]:
        async with self.sessions() as session, session.begin():
            await self._tenant(session, tenant_id)
            rows = (await session.execute(select(RmSyncJobEvent).where(
                RmSyncJobEvent.tenant_id == tenant_id, RmSyncJobEvent.job_id == job_id
            ).order_by(RmSyncJobEvent.created_at).limit(max(1, min(limit, 500))))).scalars()
            return [{
                'event_type': row.event_type, 'severity': row.severity,
                'details': {
                    key: value for key, value in (row.details or {}).items()
                    if key not in {"worker_id", "traceback", "raw_error", "payload", "response", "credentials", "authorization"}
                }, 'created_at': row.created_at.isoformat(),
            } for row in rows]

    async def metrics(self, *, tenant_id: str) -> dict:
        async with self.sessions() as session, session.begin():
            await self._tenant(session, tenant_id)
            counts = (await session.execute(
                select(RmSyncJob.status, func.count()).where(
                    RmSyncJob.tenant_id == tenant_id
                ).group_by(RmSyncJob.status)
            )).all()
            average_seconds = (await session.execute(
                select(func.avg(extract("epoch", RmSyncJob.finished_at - RmSyncJob.started_at))).where(
                    RmSyncJob.tenant_id == tenant_id,
                    RmSyncJob.finished_at.is_not(None),
                    RmSyncJob.started_at.is_not(None),
                )
            )).scalar_one_or_none()
            by_status = {status: count for status, count in counts}
            return {
                "tenant_id": tenant_id,
                "jobs_by_status": by_status,
                "queue_depth": by_status.get("queued", 0) + by_status.get("retry_wait", 0),
                "active_jobs": by_status.get("running", 0) + by_status.get("cancel_requested", 0),
                "average_duration_seconds": float(average_seconds) if average_seconds is not None else None,
            }


Executor = Callable[[dict, Callable[[], Awaitable[bool]], Callable[[], Awaitable[bool]], Callable[[str], Awaitable[None]]], Awaitable[dict | None]]


class RMSyncWorker:
    def __init__(self, queue: RMPostgresSyncQueue, executor: Executor, *, worker_id: str, tenant_ids: tuple[str, ...]):
        if not tenant_ids:
            raise ValueError('O worker precisa receber ao menos um tenant autorizado.')
        self.queue = queue
        self.executor = executor
        self.worker_id = worker_id
        self.tenant_ids = tenant_ids
        self._tenant_cursor = 0

    async def run_once(self) -> bool:
        job = None
        tenant_count = len(self.tenant_ids)
        for offset in range(tenant_count):
            index = (self._tenant_cursor + offset) % tenant_count
            tenant_id = self.tenant_ids[index]
            job = await self.queue.claim(tenant_id=tenant_id, worker_id=self.worker_id)
            if job is not None:
                self._tenant_cursor = (index + 1) % tenant_count
                break
        if job is None:
            self._tenant_cursor = (self._tenant_cursor + 1) % tenant_count
            return False

        async def heartbeat() -> bool:
            return await self.queue.heartbeat(
                tenant_id=job["tenant_id"], job_id=job["id"], worker_id=self.worker_id
            )

        async def cancelled() -> bool:
            return await self.queue.cancellation_requested(
                tenant_id=job["tenant_id"], job_id=job["id"]
            )

        async def attach_snapshot(snapshot_run_id: str) -> None:
            await self.queue.attach_snapshot_run(
                tenant_id=job["tenant_id"], job_id=job["id"],
                worker_id=self.worker_id, snapshot_run_id=snapshot_run_id,
            )

        lease_lost = asyncio.Event()

        async def renew_lease() -> None:
            try:
                while True:
                    await asyncio.sleep(30)
                    if not await heartbeat():
                        lease_lost.set()
                        return
            except asyncio.CancelledError:
                raise
            except Exception:
                lease_lost.set()

        async def fail_if_still_owner(exc: BaseException) -> None:
            try:
                await self.queue.fail(
                    tenant_id=job["tenant_id"], job_id=job["id"], worker_id=self.worker_id,
                    exc=exc, attempt=job["attempt"], max_attempts=job["max_attempts"],
                )
            except RMJobConflict:
                # A newer worker owns the lease; the stale worker must not mutate its job.
                return

        heartbeat_task = asyncio.create_task(renew_lease())
        try:
            if await cancelled():
                raise RMJobCancelled()
            result = await self.executor(job, heartbeat, cancelled, attach_snapshot)
            if lease_lost.is_set() or not await heartbeat():
                if await cancelled():
                    raise RMJobCancelled()
                raise RMJobConflict("Lease do worker foi perdido; publicação bloqueada.")
            if await cancelled():
                await self.queue.request_cancel(tenant_id=job["tenant_id"], job_id=job["id"])
            await self.queue.finish(
                tenant_id=job["tenant_id"], job_id=job["id"],
                worker_id=self.worker_id,
                snapshot_run_id=(result or {}).get("snapshot_run_id"),
            )
        except RMJobCancelled as exc:
            await fail_if_still_owner(exc)
        except Exception as exc:
            await fail_if_still_owner(exc)
        finally:
            heartbeat_task.cancel()
            await asyncio.gather(heartbeat_task, return_exceptions=True)
        return True

    async def serve(self, *, poll_seconds: float = 2.0, once: bool = False) -> None:
        while True:
            processed = await self.run_once()
            if once:
                return
            if not processed:
                await asyncio.sleep(max(0.2, poll_seconds))
