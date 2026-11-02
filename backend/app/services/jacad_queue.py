"""Resumable Redis-backed JACAD sync jobs. Queue payloads never contain credentials."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from redis.asyncio import Redis
from sqlalchemy import select

from app.core.config import get_settings
from app.core.auth import _set_tenant_rls_context
from app.db.session import AsyncSessionLocal
from app.models.jacad_connection import TenantJacadConnection
from app.models.student import Student
from app.services.connectors import get_connector, ingest_records
from app.services.connectors.jacad_mapping import enrich_jacad_students
from app.services.connectors.jacad_api import JacadApiClient, decrypt_api_token

logger = logging.getLogger(__name__)
PREFIX = "beacon:jacad:job:"
ACTIVE = "beacon:jacad:active:"
CHECKPOINT = ":checkpoint:"


def redis_client() -> Redis:
    return Redis.from_url(get_settings().redis_url, decode_responses=True)


def _key(job_id: str) -> str:
    return PREFIX + job_id


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


async def get_jacad_job(job_id: str, *, tenant_id: str | None = None, redis: Redis | None = None):
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


async def enqueue_jacad_sync(*, tenant_id: str, tenant_slug: str | None):
    settings = get_settings()
    redis = redis_client()
    try:
        active_key = ACTIVE + tenant_id
        active_id = await redis.get(active_key)
        if active_id:
            existing = await get_jacad_job(active_id, tenant_id=tenant_id, redis=redis)
            if existing and existing.get("status") in {"queued", "running", "retrying"}:
                return {**existing, "deduplicated": True}
            await redis.delete(active_key)
        job_id = str(uuid4())
        if not await redis.set(active_key, job_id, ex=settings.jacad_job_ttl_seconds, nx=True):
            raise RuntimeError("Já existe uma sincronização JACAD em andamento.")
        now = int(time.time())
        progress = {
            "stage": "queued", "percent": 0, "students": 0, "enrollments": 0,
            "financial_summaries": 0, "contracts_total": 0, "contracts_done": 0,
            "discipline_enrollments_total": 0, "discipline_enrollments_done": 0,
            "assessment_groups_total": 0, "assessment_groups_done": 0,
        }
        await redis.hset(_key(job_id), mapping={
            "tenant_id": tenant_id, "tenant_slug": tenant_slug or "",
            "status": "queued", "attempt": "0",
            "max_attempts": str(settings.jacad_max_attempts),
            "progress": _json(progress), "created_at": str(now), "updated_at": str(now),
        })
        await redis.expire(_key(job_id), settings.jacad_job_ttl_seconds)
        await redis.rpush(settings.jacad_queue_name, job_id)
        return await get_jacad_job(job_id, tenant_id=tenant_id, redis=redis)
    finally:
        await redis.aclose()


async def retry_jacad_sync(job_id: str, *, tenant_id: str):
    settings = get_settings()
    redis = redis_client()
    try:
        job = await get_jacad_job(job_id, tenant_id=tenant_id, redis=redis)
        if not job:
            return None
        if job.get("status") != "failed":
            raise ValueError("Somente sincronizações com falha podem ser retomadas.")
        if not await redis.set(ACTIVE + tenant_id, job_id, ex=settings.jacad_job_ttl_seconds, nx=True):
            raise ValueError("Já existe uma sincronização JACAD em andamento.")
        await _update(redis, job_id, status="queued", attempt=0, last_error="")
        await redis.rpush(settings.jacad_queue_name, job_id)
        return await get_jacad_job(job_id, tenant_id=tenant_id, redis=redis)
    finally:
        await redis.aclose()


async def _done(redis: Redis, job_id: str, stage: str, item: str) -> bool:
    return bool(await redis.sismember(_key(job_id) + CHECKPOINT + stage, item))


async def _mark(redis: Redis, job_id: str, stage: str, items: list[str]):
    if items:
        key = _key(job_id) + CHECKPOINT + stage
        await redis.sadd(key, *items)
        await redis.expire(key, get_settings().jacad_job_ttl_seconds)


def _deep_merge(target: dict, patch: dict) -> dict:
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            target[key] = _deep_merge(dict(target[key]), value)
        else:
            target[key] = value
    return target


async def _save_metadata(tenant_id: str, updates: dict[str, dict[str, Any]]):
    if not updates:
        return
    async with AsyncSessionLocal() as session:
        await _set_tenant_rls_context(session, tenant_id)
        rows = list((await session.execute(select(Student).where(
            Student.tenant_id == tenant_id, Student.matricula.in_(list(updates))
        ))).scalars().all())
        for student in rows:
            raw = dict(student.raw_data or {})
            raw["jacad"] = _deep_merge(dict(raw.get("jacad") or {}), updates[student.matricula])
            student.raw_data = raw
        await session.commit()


async def _run_sync(job_id: str, redis: Redis):
    job = await get_jacad_job(job_id, redis=redis)
    if not job:
        raise RuntimeError("Job JACAD não encontrado.")
    tenant_id, tenant_slug = job["tenant_id"], job.get("tenant_slug") or None
    settings = get_settings()
    progress = dict(job.get("progress") or {})
    result = dict(job.get("result") or {})

    async with AsyncSessionLocal() as session:
        await _set_tenant_rls_context(session, tenant_id)
        connection = (await session.execute(select(TenantJacadConnection).where(
            TenantJacadConnection.tenant_id == tenant_id,
            TenantJacadConnection.is_enabled.is_(True),
        ))).scalar_one_or_none()
        if not connection or connection.default_org_id is None:
            raise RuntimeError("Configure uma conexão JACAD ativa com ID da organização.")
        base_url, token, org_id = connection.base_url, decrypt_api_token(connection.encrypted_api_token), connection.default_org_id

    client = JacadApiClient(base_url, token)
    semaphore = asyncio.Semaphore(settings.jacad_sync_concurrency)
    try:
        # Stage 1: canonical base data. Re-ingestion is idempotent by tenant + RA.
        if not progress.get("base_complete"):
            await _update(redis, job_id, status="running", progress={**progress, "stage": "base", "percent": 5})
            source_students = await client.fetch_students(org_id=org_id)
            enrollments = await client.fetch_enrollments(org_id=org_id)
            summaries = await client.fetch_financial_summaries(org_id=org_id)
            enriched, metadata = enrich_jacad_students(source_students, enrollments, summaries)
            records = get_connector("jacad").transform({"elements": enriched})
            if not records:
                raise RuntimeError("A consulta JACAD terminou sem alunos válidos para ingestão.")
            async with AsyncSessionLocal() as session:
                ingestion = await ingest_records(
                    session, records=records, source="jacad",
                    filename="jacad_academic_financial_sync.json", auto_score=False,
                    tenant_id=tenant_id, tenant_slug=tenant_slug,
                )
                await _set_tenant_rls_context(session, tenant_id)
                imported = list((await session.execute(select(Student).where(
                    Student.tenant_id == tenant_id,
                    Student.matricula.in_([r["matricula"] for r in records]),
                ))).scalars().all())
                imported_at = datetime.now(timezone.utc).isoformat()
                fields = ("status_aluno", "curso", "turma", "status_financeiro",
                          "dias_atraso_boleto", "recorrencia_atrasos", "saldo_devedor")
                for student in imported:
                    raw = dict(student.raw_data or {})
                    raw["jacad"] = metadata.get(student.matricula, {})
                    provenance = dict(raw.get("_mira_provenance") or {})
                    for field in fields:
                        if getattr(student, field, None) is not None or field in {
                            "status_financeiro", "dias_atraso_boleto", "recorrencia_atrasos"
                        }:
                            provenance[field] = {
                                "source_type": "jacad_api",
                                "source_filename": "jacad_academic_financial_sync",
                                "source_batch_id": str(ingestion["batch"].id),
                                "imported_at": imported_at, "observed_at": None,
                                "observed_at_source_column": None,
                                "freshness_basis": "source_observation_timestamp_unavailable",
                            }
                    raw["_mira_provenance"] = provenance
                    student.raw_data = raw
                await session.commit()
            result.update({
                "source_records": len(source_students),
                "students_imported": ingestion.get("students_imported", 0),
                "enrollments_received": len(enrollments),
                "financial_summaries_received": len(summaries),
                "students_with_financial_status": sum(bool(r.get("status_financeiro")) for r in enriched),
            })
            progress.update({
                "base_complete": True, "stage": "financial_details", "percent": 25,
                "students": len(source_students), "enrollments": len(enrollments),
                "financial_summaries": len(summaries),
            })
            await _update(redis, job_id, progress=progress, result=result)

        async with AsyncSessionLocal() as session:
            await _set_tenant_rls_context(session, tenant_id)
            students = list((await session.execute(select(Student).where(
                Student.tenant_id == tenant_id, Student.is_active.is_(True)
            ))).scalars().all())

        contract_to_ra: dict[str, str] = {}
        enrollment_to_ra: dict[str, str] = {}
        for student in students:
            jacad = (student.raw_data or {}).get("jacad") or {}
            for enrollment in jacad.get("matriculas", []):
                if enrollment.get("id_contrato") is not None:
                    contract_to_ra[str(enrollment["id_contrato"])] = student.matricula
                if enrollment.get("id_matricula") is not None:
                    enrollment_to_ra[str(enrollment["id_matricula"])] = student.matricula

        # Stage 2: detailed installments, with bounded concurrency and DB-before-checkpoint.
        contracts = sorted(contract_to_ra.items())
        pending = [(cid, ra) for cid, ra in contracts if not await _done(redis, job_id, "contracts", cid)]
        progress.update({"stage": "financial_details", "contracts_total": len(contracts),
                         "contracts_done": len(contracts)-len(pending), "percent": 30})
        await _update(redis, job_id, progress=progress)
        for offset in range(0, len(pending), settings.jacad_sync_concurrency * 4):
            chunk = pending[offset:offset + settings.jacad_sync_concurrency * 4]
            async def fetch_installments(cid: str):
                async with semaphore:
                    return await client.fetch_contract_installments(int(cid))
            fetched = await asyncio.gather(*(fetch_installments(cid) for cid, _ in chunk))
            updates: dict[str, dict[str, Any]] = {}
            for (cid, ra), rows in zip(chunk, fetched):
                normalized = [{
                    "id_transacao": x.get("idTransacao"), "valor": x.get("valor"),
                    "valor_pago": x.get("valorPago"), "situacao": x.get("situacao"),
                    "data_vencimento": x.get("dataVencimento"),
                    "data_pagamento": x.get("dataPagamento"),
                } for x in rows]
                updates.setdefault(ra, {}).setdefault("installments_by_contract", {})[cid] = normalized
            await _save_metadata(tenant_id, updates)
            await _mark(redis, job_id, "contracts", [cid for cid, _ in chunk])
            progress["contracts_done"] += len(chunk)
            progress["percent"] = 30 + int(20 * progress["contracts_done"] / max(1, len(contracts)))
            await _update(redis, job_id, progress=progress)

        # Stage 3: discipline results per enrollment. Preserve raw scale and counts.
        async with AsyncSessionLocal() as session:
            await _set_tenant_rls_context(session, tenant_id)
            students = list((await session.execute(select(Student).where(
                Student.tenant_id == tenant_id, Student.is_active.is_(True)
            ))).scalars().all())
        enrollment_to_ra = {}
        for student in students:
            for enrollment in ((student.raw_data or {}).get("jacad") or {}).get("matriculas", []):
                if enrollment.get("id_matricula") is not None:
                    enrollment_to_ra[str(enrollment["id_matricula"])] = student.matricula
        enrollments = sorted(enrollment_to_ra.items())
        pending = [(eid, ra) for eid, ra in enrollments if not await _done(redis, job_id, "disciplines", eid)]
        progress.update({"stage": "academic_disciplines", "discipline_enrollments_total": len(enrollments),
                         "discipline_enrollments_done": len(enrollments)-len(pending), "percent": 55})
        await _update(redis, job_id, progress=progress)
        for offset in range(0, len(pending), settings.jacad_sync_concurrency * 4):
            chunk = pending[offset:offset + settings.jacad_sync_concurrency * 4]
            async def fetch_disciplines(eid: str):
                async with semaphore:
                    return await client.fetch_enrollment_disciplines(int(eid))
            fetched = await asyncio.gather(*(fetch_disciplines(eid) for eid, _ in chunk))
            updates = {}
            for (eid, ra), rows in zip(chunk, fetched):
                updates.setdefault(ra, {}).setdefault("academic_disciplines_by_enrollment", {})[eid] = [{
                    "id_matricula_disciplina": x.get("idMatriculaDisciplina"),
                    "id_disciplina_professor": x.get("idDisciplinaProfessor"),
                    "id_turma_disciplina": x.get("idTurmaDisciplina"),
                    "id_turma_matricula": x.get("idTurmaMatricula"),
                    "id_aluno": x.get("idAluno"), "status": x.get("statusMatriculaDisciplina"),
                    "disciplina": x.get("disciplina"), "professor": x.get("professor"),
                    "periodo_letivo": x.get("periodoLetivo"), "turma": x.get("turma"),
                    "quantidade_aulas": x.get("quantAulas"), "quantidade_faltas": x.get("quantFaltas"),
                    "quantidade_faltas_transferencia": x.get("quantFaltasTransferencia"),
                    "frequencia": x.get("frequencia"), "media_final": x.get("mediaFinal"),
                    "nota_final": x.get("notaFinal"), "nota_exame": x.get("notaExame"),
                    "data_modificacao": x.get("dataModificacao"),
                } for x in rows]
            await _save_metadata(tenant_id, updates)
            await _mark(redis, job_id, "disciplines", [eid for eid, _ in chunk])
            progress["discipline_enrollments_done"] += len(chunk)
            progress["percent"] = 55 + int(20 * progress["discipline_enrollments_done"] / max(1, len(enrollments)))
            await _update(redis, job_id, progress=progress)

        # Stage 4: itemized assessment notes, one request per unique class/discipline pair.
        async with AsyncSessionLocal() as session:
            await _set_tenant_rls_context(session, tenant_id)
            students = list((await session.execute(select(Student).where(
                Student.tenant_id == tenant_id, Student.is_active.is_(True)
            ))).scalars().all())
        pairs: dict[str, tuple[int, int]] = {}
        for student in students:
            jacad = (student.raw_data or {}).get("jacad") or {}
            for rows in jacad.get("academic_disciplines_by_enrollment", {}).values():
                for row in rows:
                    class_id, discipline_id = row.get("id_turma_disciplina"), row.get("id_disciplina_professor")
                    if class_id is not None and discipline_id is not None:
                        key = f"{int(class_id)}:{int(discipline_id)}"
                        pairs[key] = (int(class_id), int(discipline_id))
        pair_items = sorted(pairs.items())
        pending = [(key, pair) for key, pair in pair_items if not await _done(redis, job_id, "assessment", key)]
        progress.update({"stage": "assessment_details", "assessment_groups_total": len(pair_items),
                         "assessment_groups_done": len(pair_items)-len(pending), "percent": 78})
        await _update(redis, job_id, progress=progress)
        for offset in range(0, len(pending), settings.jacad_sync_concurrency * 2):
            chunk = pending[offset:offset + settings.jacad_sync_concurrency * 2]
            async def fetch_notes(pair: tuple[int, int]):
                async with semaphore:
                    return await client.fetch_assessment_notes(pair[0], pair[1])
            fetched = await asyncio.gather(*(fetch_notes(pair) for _, pair in chunk))
            updates = {}
            for (key, _), rows in zip(chunk, fetched):
                for row in rows:
                    ra = str(row.get("ra") or "").strip()
                    if not ra:
                        continue
                    updates.setdefault(ra, {}).setdefault("assessment_notes_by_class_discipline", {})[key] = [{
                        "id_matricula": x.get("idMatricula"),
                        "id_matricula_disciplina": x.get("idMatriculaDisciplina"),
                        "status_matricula": x.get("statusMatricula"),
                        "status_disciplina": x.get("statusMatriculaDisciplina"),
                        "media_disciplina": x.get("mediaMatriculaDisciplina"),
                        "itens_notas": x.get("itensNotas") or [],
                    } for x in rows if str(x.get("ra") or "").strip() == ra]
            await _save_metadata(tenant_id, updates)
            await _mark(redis, job_id, "assessment", [key for key, _ in chunk])
            progress["assessment_groups_done"] += len(chunk)
            progress["percent"] = 78 + int(17 * progress["assessment_groups_done"] / max(1, len(pair_items)))
            await _update(redis, job_id, progress=progress)

        progress.update({"stage": "completed", "percent": 100})
        result.update({
            "contracts_with_installments": len(contracts),
            "discipline_enrollments": len(enrollments),
            "assessment_groups": len(pair_items),
            "scoring": "disabled_until_predictive_coverage_is_complete",
        })
        await _update(redis, job_id, status="completed", progress=progress, result=result, last_error="")
        async with AsyncSessionLocal() as session:
            await _set_tenant_rls_context(session, tenant_id)
            connection = (await session.execute(select(TenantJacadConnection).where(
                TenantJacadConnection.tenant_id == tenant_id
            ))).scalar_one_or_none()
            if connection:
                connection.status = "connected"
                connection.last_sync_at = datetime.now(timezone.utc)
                connection.last_sync_status = "success"
                connection.last_sync_records = int(result.get("students_imported", 0))
                connection.last_error = None
                await session.commit()
        await redis.delete(ACTIVE + tenant_id)
    finally:
        await client.close()


async def process_jacad_sync_job(job_id: str, redis: Redis) -> bool:
    settings = get_settings()
    job = await get_jacad_job(job_id, redis=redis)
    if not job or job.get("status") in {"completed", "failed"}:
        return True
    lock_key = _key(job_id) + ":lock"
    if not await redis.set(lock_key, "1", ex=3600, nx=True):
        return False
    try:
        job = await get_jacad_job(job_id, redis=redis)
        attempt = int(job.get("attempt", 0)) + 1
        await _update(redis, job_id, status="running", attempt=attempt)
        try:
            await _run_sync(job_id, redis)
            return True
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"[:1200]
            if attempt < int(job.get("max_attempts", settings.jacad_max_attempts)):
                delay = settings.jacad_retry_backoff_seconds * (2 ** (attempt - 1))
                await _update(redis, job_id, status="retrying", attempt=attempt,
                              last_error=error, next_retry_at=int(time.time()) + delay)
                await redis.zadd(settings.jacad_queue_name + ":delayed", {job_id: time.time() + delay})
                return False
            await _update(redis, job_id, status="failed", attempt=attempt, last_error=error)
            tenant_id = job["tenant_id"]
            async with AsyncSessionLocal() as session:
                await _set_tenant_rls_context(session, tenant_id)
                connection = (await session.execute(select(TenantJacadConnection).where(
                    TenantJacadConnection.tenant_id == tenant_id
                ))).scalar_one_or_none()
                if connection:
                    connection.last_sync_status = "failed"
                    connection.last_error = error
                    await session.commit()
            await redis.delete(ACTIVE + tenant_id)
            logger.exception("jacad_sync_failed", extra={"job_id": job_id, "tenant_id": tenant_id})
            return True
    finally:
        await redis.delete(lock_key)


async def promote_due_jacad_retries(redis: Redis) -> int:
    settings = get_settings()
    key = settings.jacad_queue_name + ":delayed"
    ids = await redis.zrangebyscore(key, min=0, max=time.time(), start=0, num=100)
    if not ids:
        return 0
    await redis.zrem(key, *ids)
    await redis.rpush(settings.jacad_queue_name, *ids)
    return len(ids)
