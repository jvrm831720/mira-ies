"""Incremental, checkpointed Sponte BI synchronization jobs."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import select

from app.core.auth import _set_tenant_rls_context
from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.models.sponte_connection import TenantSponteConnection
from app.models.student import Student
from app.services.connectors import get_connector, ingest_records
from app.services.connectors.jacad_api import decrypt_api_token
from app.services.connectors.sponte_api import SponteApiClient, SponteQuotaDeferred
from app.services.connectors.sponte_mapping import (
    aluno_id, build_student_payloads, compact_row, pick, record_id,
)

logger = logging.getLogger(__name__)
PREFIX = "beacon:sponte:job:"
ACTIVE = "beacon:sponte:active:"
LAST = "beacon:sponte:last:"
CHECKPOINT = ":checkpoint:"


def redis_client() -> Redis:
    return Redis.from_url(get_settings().redis_url, decode_responses=True)


def _key(job_id: str) -> str:
    return PREFIX + job_id


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


async def get_sponte_job(job_id: str, *, tenant_id: str | None = None, redis: Redis | None = None):
    owns = redis is None
    client = redis or redis_client()
    try:
        raw = await client.hgetall(_key(job_id))
        if not raw or (tenant_id and raw.get("tenant_id") != tenant_id):
            return None
        job = dict(raw)
        job["id"] = job_id
        for field in ("progress", "result"):
            if field in job:
                try:
                    job[field] = json.loads(job[field])
                except json.JSONDecodeError:
                    pass
        for field in ("attempt", "max_attempts", "created_at", "updated_at"):
            if field in job:
                job[field] = int(float(job[field]))
        return job
    finally:
        if owns:
            await client.aclose()


async def _update(redis: Redis, job_id: str, **fields: Any):
    fields["updated_at"] = int(time.time())
    await redis.hset(_key(job_id), mapping={
        k: _json(v) if isinstance(v, (dict, list)) else str(v) for k, v in fields.items()
    })
    await redis.expire(_key(job_id), get_settings().sponte_job_ttl_seconds)
    status = fields.get("status") or await redis.hget(_key(job_id), "status")
    if status == "running":
        await redis.expire(_key(job_id) + ":lock", 600)


async def enqueue_sponte_sync(*, tenant_id: str, tenant_slug: str | None):
    settings = get_settings()
    redis = redis_client()
    try:
        active_id = await redis.get(ACTIVE + tenant_id)
        if active_id:
            active = await get_sponte_job(active_id, tenant_id=tenant_id, redis=redis)
            if active and active.get("status") in {"queued", "running", "retrying"}:
                return {**active, "deduplicated": True}
            await redis.delete(ACTIVE + tenant_id)
        job_id = str(uuid4())
        if not await redis.set(ACTIVE + tenant_id, job_id, ex=settings.sponte_job_ttl_seconds, nx=True):
            raise RuntimeError("Já existe uma sincronização Sponte em andamento.")
        now = int(time.time())
        progress = {"stage": "queued", "endpoint": None, "percent": 0, "pages_done": 0, "pages_total": 0}
        await redis.hset(_key(job_id), mapping={
            "tenant_id": tenant_id, "tenant_slug": tenant_slug or "",
            "status": "queued", "attempt": "0", "max_attempts": str(settings.sponte_max_attempts),
            "progress": _json(progress), "result": _json({"endpoints": {}}),
            "created_at": str(now), "updated_at": str(now),
        })
        await redis.expire(_key(job_id), settings.sponte_job_ttl_seconds)
        await redis.set(LAST + tenant_id, job_id, ex=settings.sponte_job_ttl_seconds)
        await redis.rpush(settings.sponte_queue_name, job_id)
        return await get_sponte_job(job_id, tenant_id=tenant_id, redis=redis)
    finally:
        await redis.aclose()


async def get_current_sponte_job(*, tenant_id: str):
    redis = redis_client()
    try:
        job_id = await redis.get(ACTIVE + tenant_id) or await redis.get(LAST + tenant_id)
        return await get_sponte_job(job_id, tenant_id=tenant_id, redis=redis) if job_id else None
    finally:
        await redis.aclose()


async def retry_sponte_sync(job_id: str, *, tenant_id: str):
    settings = get_settings()
    redis = redis_client()
    try:
        job = await get_sponte_job(job_id, tenant_id=tenant_id, redis=redis)
        if not job:
            return None
        if job.get("status") != "failed":
            raise ValueError("Somente sincronizações Sponte com falha podem ser retomadas.")
        if not await redis.set(ACTIVE + tenant_id, job_id, ex=settings.sponte_job_ttl_seconds, nx=True):
            raise ValueError("Já existe uma sincronização Sponte em andamento.")
        await _update(redis, job_id, status="queued", attempt=0, last_error="")
        await redis.set(LAST + tenant_id, job_id, ex=settings.sponte_job_ttl_seconds)
        await redis.rpush(settings.sponte_queue_name, job_id)
        return await get_sponte_job(job_id, tenant_id=tenant_id, redis=redis)
    finally:
        await redis.aclose()


async def _checkpoint_done(redis: Redis, job_id: str, endpoint: str, page: int) -> bool:
    return bool(await redis.sismember(f"{_key(job_id)}{CHECKPOINT}{endpoint}", str(page)))


async def _checkpoint_mark(redis: Redis, job_id: str, endpoint: str, page: int):
    key = f"{_key(job_id)}{CHECKPOINT}{endpoint}"
    await redis.sadd(key, str(page))
    await redis.expire(key, get_settings().sponte_job_ttl_seconds)


async def _endpoint_done(redis: Redis, job_id: str, endpoint: str) -> bool:
    return bool(await redis.sismember(f"{_key(job_id)}:endpoints_done", endpoint))


async def _endpoint_mark(redis: Redis, job_id: str, endpoint: str):
    key = f"{_key(job_id)}:endpoints_done"
    await redis.sadd(key, endpoint)
    await redis.expire(key, get_settings().sponte_job_ttl_seconds)


async def _reserve_window(redis: Redis, key: str, *, limit: int, window_ms: int) -> int:
    script = """
    local now = tonumber(ARGV[1])
    local window = tonumber(ARGV[2])
    local limit = tonumber(ARGV[3])
    redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now - window)
    local count = redis.call('ZCARD', KEYS[1])
    if count >= limit then
      local first = redis.call('ZRANGE', KEYS[1], 0, 0, 'WITHSCORES')
      return tonumber(first[2]) + window - now
    end
    redis.call('ZADD', KEYS[1], now, ARGV[4])
    redis.call('PEXPIRE', KEYS[1], window + 60000)
    return 0
    """
    now_ms = int(time.time() * 1000)
    return int(await redis.eval(script, 1, key, now_ms, window_ms, limit, f"{now_ms}:{uuid4()}"))


async def _request_guard(redis: Redis, credential_scope: str):
    settings = get_settings()
    while True:
        wait_ms = await _reserve_window(
            redis, "beacon:sponte:rate:global",
            limit=settings.sponte_global_requests_per_second, window_ms=1000,
        )
        if wait_ms <= 0:
            break
        await asyncio.sleep(wait_ms / 1000 + 0.02)
    wait_ms = await _reserve_window(
        redis, f"beacon:sponte:rate:key:{credential_scope}",
        limit=settings.sponte_requests_per_minute, window_ms=60000
    )
    if wait_ms > 0:
        raise SponteQuotaDeferred(wait_ms / 1000 + 2)


async def _persist_catalog_page(
    *, tenant_id: str, endpoint: str, items: list[dict[str, Any]],
) -> tuple[int, list[str]]:
    if not items:
        return 0, []
    bucket_name = endpoint
    id_field = {"cursos": "curso_id", "turmas": "turma_id", "estagios": "estagio_id"}[endpoint]
    async with AsyncSessionLocal() as session:
        await _set_tenant_rls_context(session, tenant_id)
        connection = (await session.execute(select(TenantSponteConnection).where(
            TenantSponteConnection.tenant_id == tenant_id
        ))).scalar_one()
        catalogs = dict(connection.sync_catalogs or {})
        bucket = dict(catalogs.get(bucket_name) or {})
        for item in items:
            compact = compact_row(endpoint, item)
            provider_id = compact.get(id_field)
            if provider_id is not None:
                bucket[str(provider_id)] = compact
        catalogs[bucket_name] = bucket
        connection.sync_catalogs = catalogs
        students = list((await session.execute(
            select(Student.matricula).where(Student.tenant_id == tenant_id)
        )).scalars().all())
        await session.commit()
    return len(items), students


async def _persist_page(
    *, tenant_id: str, tenant_slug: str | None, endpoint: str,
    items: list[dict[str, Any]], page_number: int, job_id: str,
) -> tuple[int, list[str]]:
    if endpoint in {"cursos", "turmas", "estagios"}:
        return await _persist_catalog_page(tenant_id=tenant_id, endpoint=endpoint, items=items)
    direct_ids = {aluno_id(item) for item in items if aluno_id(item)}
    contract_ids = {
        str(value) for item in items
        if (value := pick(item, "ContratoID", "IdContrato")) is not None
    }
    if not direct_ids and not contract_ids:
        return 0, []
    imported = 0
    if endpoint == "alunos":
        records = get_connector("sponte").transform(items)
        if records:
            async with AsyncSessionLocal() as session:
                await _set_tenant_rls_context(session, tenant_id)
                await ingest_records(
                    session, records=records, source="sponte",
                    filename=f"sponte_alunos_page_{page_number}.json",
                    auto_score=False, tenant_id=tenant_id, tenant_slug=tenant_slug,
                )
                imported = len(records)

    async with AsyncSessionLocal() as session:
        await _set_tenant_rls_context(session, tenant_id)
        contract_to_ra: dict[str, str] = {}
        if contract_ids:
            all_students = list((await session.execute(
                select(Student).where(Student.tenant_id == tenant_id)
            )).scalars().all())
            for existing in all_students:
                contracts = ((existing.raw_data or {}).get("sponte") or {}).get("contratos") or {}
                for contract in contracts.values():
                    contract_id = contract.get("contrato_id")
                    if contract_id is not None:
                        contract_to_ra[str(contract_id)] = existing.matricula
        resolved_ids = set(direct_ids)
        for item in items:
            if not aluno_id(item):
                contract_id = pick(item, "ContratoID", "IdContrato")
                if contract_id is not None and str(contract_id) in contract_to_ra:
                    resolved_ids.add(contract_to_ra[str(contract_id)])
        students = list((await session.execute(select(Student).where(
            Student.tenant_id == tenant_id, Student.matricula.in_(list(resolved_ids))
        ))).scalars().all())
        by_id = {student.matricula: student for student in students}
        imported_at = datetime.now(timezone.utc).isoformat()
        affected_ids = set()
        for item in items:
            sid = aluno_id(item)
            if not sid:
                contract_id = item.get("ContratoID") or item.get("IdContrato")
                sid = contract_to_ra.get(str(contract_id)) if contract_id is not None else None
            student = by_id.get(sid or "")
            if not student:
                continue
            affected_ids.add(student.matricula)
            raw = dict(student.raw_data or {})
            sponte = dict(raw.get("sponte") or {})
            if endpoint == "alunos":
                sponte["profile"] = compact_row("alunos", item)
            else:
                bucket = dict(sponte.get(endpoint) or {})
                bucket[record_id(endpoint, item)] = compact_row(endpoint, item)
                sponte[endpoint] = bucket
            raw["sponte"] = sponte
            provenance = dict(raw.get("_mira_provenance") or {})
            provenance[f"sponte.{endpoint}"] = {
                "source_type": "sponte_bi_api",
                "source_filename": f"sponte_{endpoint}",
                "source_batch_id": job_id,
                "imported_at": imported_at,
                "observed_at": None,
                "observed_at_source_column": None,
                "freshness_basis": "source_observation_timestamp_unavailable",
            }
            raw["_mira_provenance"] = provenance
            student.raw_data = raw
        await session.commit()
    return imported, sorted(affected_ids)

async def _update_watermark(tenant_id: str, endpoint: str, as_of: date):
    async with AsyncSessionLocal() as session:
        await _set_tenant_rls_context(session, tenant_id)
        connection = (await session.execute(select(TenantSponteConnection).where(
            TenantSponteConnection.tenant_id == tenant_id
        ))).scalar_one()
        watermarks = dict(connection.sync_watermarks or {})
        watermarks[endpoint] = as_of.isoformat()
        connection.sync_watermarks = watermarks
        await session.commit()


async def _derive_affected_students(tenant_id: str, affected_ids: list[str], job_id: str):
    if not affected_ids:
        return 0
    as_of = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    async with AsyncSessionLocal() as session:
        await _set_tenant_rls_context(session, tenant_id)
        connection = (await session.execute(select(TenantSponteConnection).where(
            TenantSponteConnection.tenant_id == tenant_id
        ))).scalar_one_or_none()
        catalogs = dict(connection.sync_catalogs or {}) if connection else {}
        students = list((await session.execute(select(Student).where(
            Student.tenant_id == tenant_id, Student.matricula.in_(affected_ids)
        ))).scalars().all())
        payloads = build_student_payloads(students, as_of=as_of, catalogs=catalogs)
        records = get_connector("sponte").transform(payloads)
        by_id = {record["matricula"]: record for record in records}
        imported_at = datetime.now(timezone.utc).isoformat()
        for student in students:
            record = by_id.get(student.matricula)
            if not record:
                continue
            for field in (
                "nome", "curso", "turma", "semestre", "forma_ingresso", "telefone", "email",
                "dias_atraso_boleto", "recorrencia_atrasos", "dias_sem_login",
                "presenca_percentual", "nota_media", "reprovacoes",
                "saldo_devedor", "status_financeiro", "status_aluno",
            ):
                if hasattr(student, field):
                    setattr(student, field, record.get(field))
            student.risk_score = None
            student.risk_level = None
            student.model_risk_score = None
            student.shap_top_factors = None
            raw = dict(student.raw_data or {})
            provenance = dict(raw.get("_mira_provenance") or {})
            for field in (
                "dias_atraso_boleto", "recorrencia_atrasos", "saldo_devedor",
                "status_financeiro", "presenca_percentual", "status_aluno",
            ):
                provenance[field] = {
                    "source_type": "sponte_bi_api",
                    "source_filename": "sponte_incremental_sync",
                    "source_batch_id": job_id,
                    "imported_at": imported_at,
                    "observed_at": (
                        (record.get("raw") or {}).get("attendance_observed_at")
                        if field == "presenca_percentual" else None
                    ),
                    "observed_at_source_column": "DataExtracao" if field == "presenca_percentual" else None,
                    "freshness_basis": "source_snapshot" if field == "presenca_percentual" else "source_observation_timestamp_unavailable",
                }
            raw["_mira_provenance"] = provenance
            student.raw_data = raw
        await session.commit()
        return len(students)


async def _run_sync(job_id: str, redis: Redis):
    job = await get_sponte_job(job_id, redis=redis)
    if not job:
        raise RuntimeError("Job Sponte não encontrado.")
    tenant_id = job["tenant_id"]
    tenant_slug = job.get("tenant_slug") or None
    settings = get_settings()
    progress = dict(job.get("progress") or {})
    result = dict(job.get("result") or {"endpoints": {}})
    as_of = datetime.now(ZoneInfo("America/Sao_Paulo")).date()

    async with AsyncSessionLocal() as session:
        await _set_tenant_rls_context(session, tenant_id)
        connection = (await session.execute(select(TenantSponteConnection).where(
            TenantSponteConnection.tenant_id == tenant_id,
            TenantSponteConnection.is_enabled.is_(True),
        ))).scalar_one_or_none()
        if not connection:
            raise RuntimeError("Configure uma conexão Sponte ativa.")
        api_key = decrypt_api_token(connection.encrypted_api_key)
        client_code = connection.client_code
        initial_date = connection.initial_extraction_date
        watermarks = dict(connection.sync_watermarks or {})

    credential_scope = hashlib.sha256(api_key.encode()).hexdigest()[:20]
    client = SponteApiClient(
        api_key, client_code,
        request_guard=lambda: _request_guard(redis, credential_scope),
    )
    affected_key = f"{_key(job_id)}:affected"
    semaphore = asyncio.Semaphore(settings.sponte_sync_concurrency)
    try:
        endpoints = (
            "alunos", "cursos", "turmas", "estagios", "contratos",
            "contratosturmasestagios", "contasreceber", "notas",
            "fatofrequenciaalunosativos", "fatoalunosativos", "followups",
        )
        for endpoint_index, endpoint in enumerate(endpoints):
            if await _endpoint_done(redis, job_id, endpoint):
                continue
            watermark = watermarks.get(endpoint)
            extraction_date = (
                max(initial_date, date.fromisoformat(watermark) - timedelta(days=1))
                if watermark else initial_date
            )
            first = await client.fetch_page(
                endpoint, extraction_date=extraction_date, page_number=1, page_size=1000
            )
            total_pages = int(first.get("totalPages") or 1)
            if total_pages > 10000:
                raise RuntimeError(f"Endpoint Sponte {endpoint} excedeu o limite seguro de 10.000 páginas.")
            total_pages = max(1, total_pages)
            progress.update({
                "stage": "extracting", "endpoint": endpoint,
                "endpoint_index": endpoint_index + 1, "endpoint_count": len(endpoints),
                "pages_total": total_pages, "pages_done": 0,
                "percent": int(endpoint_index / len(endpoints) * 85),
            })
            await _update(redis, job_id, status="running", progress=progress)

            async def persist(page_number: int, payload: dict[str, Any]):
                if await _checkpoint_done(redis, job_id, endpoint, page_number):
                    return 0
                items = [item for item in payload.get("items", []) if isinstance(item, dict)]
                imported, ids = await _persist_page(
                    tenant_id=tenant_id, tenant_slug=tenant_slug, endpoint=endpoint,
                    items=items, page_number=page_number, job_id=job_id,
                )
                if ids:
                    await redis.sadd(affected_key, *ids)
                    await redis.expire(affected_key, settings.sponte_job_ttl_seconds)
                await _checkpoint_mark(redis, job_id, endpoint, page_number)
                result.setdefault("endpoints", {})[endpoint] = (
                    int(result.get("endpoints", {}).get(endpoint, 0)) + len(items)
                )
                progress["pages_done"] += 1
                progress["percent"] = int((endpoint_index + progress["pages_done"] / total_pages) / len(endpoints) * 85)
                await _update(redis, job_id, progress=progress, result=result)
                return imported

            if not await _checkpoint_done(redis, job_id, endpoint, 1):
                await persist(1, first)
            else:
                progress["pages_done"] = 1
            for offset in range(2, total_pages + 1, settings.sponte_sync_concurrency):
                page_numbers = list(range(offset, min(total_pages + 1, offset + settings.sponte_sync_concurrency)))
                pending = [n for n in page_numbers if not await _checkpoint_done(redis, job_id, endpoint, n)]
                already_done = len(page_numbers) - len(pending)
                progress["pages_done"] += already_done
                if not pending:
                    await _update(redis, job_id, progress=progress)
                    continue
                async def fetch_page(number: int):
                    async with semaphore:
                        return await client.fetch_page(
                            endpoint, extraction_date=extraction_date,
                            page_number=number, page_size=1000,
                        )
                fetched = await asyncio.gather(*(fetch_page(n) for n in pending), return_exceptions=True)
                failures = []
                for number, payload in zip(pending, fetched):
                    if isinstance(payload, Exception):
                        failures.append(payload)
                        continue
                    await persist(number, payload)
                if failures:
                    raise failures[0]

            await _endpoint_mark(redis, job_id, endpoint)
            await _update_watermark(tenant_id, endpoint, as_of)
            watermarks[endpoint] = as_of.isoformat()
            result.setdefault("watermarks", {})[endpoint] = as_of.isoformat()

        affected_ids = sorted(await redis.smembers(affected_key))
        students_updated = await _derive_affected_students(tenant_id, affected_ids, job_id)
        result["students_updated"] = students_updated
        result["scoring"] = "disabled_until_predictive_semantics_are_homologated"
        progress.update({"stage": "completed", "percent": 100})
        await _update(redis, job_id, status="completed", progress=progress, result=result, last_error="")
        async with AsyncSessionLocal() as session:
            await _set_tenant_rls_context(session, tenant_id)
            connection = (await session.execute(select(TenantSponteConnection).where(
                TenantSponteConnection.tenant_id == tenant_id
            ))).scalar_one_or_none()
            if connection:
                connection.status = "connected"
                connection.last_sync_at = datetime.now(timezone.utc)
                connection.last_sync_status = "success"
                connection.last_sync_records = students_updated
                connection.last_error = None
                await session.commit()
        await redis.delete(ACTIVE + tenant_id)
    finally:
        await client.close()


async def process_sponte_sync_job(job_id: str, redis: Redis) -> bool:
    settings = get_settings()
    job = await get_sponte_job(job_id, redis=redis)
    if not job or job.get("status") in {"completed", "failed"}:
        return True
    lock_key = _key(job_id) + ":lock"
    if not await redis.set(lock_key, "1", ex=600, nx=True):
        return False
    try:
        job = await get_sponte_job(job_id, redis=redis)
        attempt = int(job.get("attempt", 0)) + 1
        await _update(redis, job_id, status="running", attempt=attempt)
        try:
            await _run_sync(job_id, redis)
            return True
        except SponteQuotaDeferred as exc:
            delay = max(60, int(exc.wait_seconds))
            await _update(redis, job_id, status="retrying", attempt=max(0, attempt - 1),
                          last_error=str(exc), next_retry_at=int(time.time()) + delay)
            await redis.zadd(settings.sponte_queue_name + ":delayed", {job_id: time.time() + delay})
            return False
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"[:1200]
            if attempt < int(job.get("max_attempts", settings.sponte_max_attempts)):
                delay = settings.sponte_retry_backoff_seconds * (2 ** (attempt - 1))
                await _update(redis, job_id, status="retrying", attempt=attempt,
                              last_error=error, next_retry_at=int(time.time()) + delay)
                await redis.zadd(settings.sponte_queue_name + ":delayed", {job_id: time.time() + delay})
                return False
            await _update(redis, job_id, status="failed", attempt=attempt, last_error=error)
            tenant_id = job["tenant_id"]
            async with AsyncSessionLocal() as session:
                await _set_tenant_rls_context(session, tenant_id)
                connection = (await session.execute(select(TenantSponteConnection).where(
                    TenantSponteConnection.tenant_id == tenant_id
                ))).scalar_one_or_none()
                if connection:
                    connection.last_sync_status = "failed"
                    connection.last_error = error
                    await session.commit()
            await redis.delete(ACTIVE + tenant_id)
            logger.exception("sponte_sync_failed", extra={"job_id": job_id, "tenant_id": tenant_id})
            return True
    finally:
        await redis.delete(lock_key)


async def promote_due_sponte_retries(redis: Redis) -> int:
    key = get_settings().sponte_queue_name + ":delayed"
    ids = await redis.zrangebyscore(key, min=0, max=time.time(), start=0, num=100)
    if not ids:
        return 0
    await redis.zrem(key, *ids)
    await redis.rpush(get_settings().sponte_queue_name, *ids)
    return len(ids)


async def requeue_stale_sponte_jobs(redis: Redis, *, stale_after_seconds: int = 600) -> int:
    now = int(time.time())
    recovered = 0
    async for raw_key in redis.scan_iter(match=PREFIX + "*"):
        key = str(raw_key)
        suffix = key[len(PREFIX):]
        if ":" in suffix:
            continue
        job = await redis.hgetall(key)
        if job.get("status") != "running":
            continue
        try:
            updated_at = int(float(job.get("updated_at", 0)))
        except (TypeError, ValueError):
            continue
        if now - updated_at < stale_after_seconds or await redis.exists(key + ":lock"):
            continue
        recovery_lock = key + ":recovery-lock"
        if not await redis.set(recovery_lock, "1", ex=30, nx=True):
            continue
        try:
            job = await redis.hgetall(key)
            if job.get("status") != "running" or await redis.exists(key + ":lock"):
                continue
            job_id = suffix
            await _update(redis, job_id, status="queued",
                          last_error="Worker interrompido; job recuperado do último checkpoint.")
            await redis.rpush(get_settings().sponte_queue_name, job_id)
            recovered += 1
        finally:
            await redis.delete(recovery_lock)
    return recovered
