"""Retention run and enqueue routes."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.orchestrator import RetentionOrchestrator, fetch_eligible_students
from app.agents.rules import decide_channels
from app.core.auth import AuthContext, require_min_role
from app.db.session import get_db
from app.services.consent import is_communication_allowed
from app.services.engagement import recommend_send_time
from app.services.retention_queue import enqueue_retention_job
from app.api.agents_common import (
    router,
    RetentionRunRequest,
    _VALID_CHANNELS,
    _VALID_RISK_LEVELS,
)


@router.post("/agents/retention/run")
async def run_retention(
    body: RetentionRunRequest,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    auth: AuthContext = Depends(require_min_role("operator")),
    db: AsyncSession = Depends(get_db),
):
    invalid_levels = [lvl for lvl in body.risk_levels if lvl not in _VALID_RISK_LEVELS]
    if invalid_levels:
        raise HTTPException(status_code=422, detail=f"risk_levels invalidos: {invalid_levels}")
    if body.channels:
        invalid_channels = [c for c in body.channels if c not in _VALID_CHANNELS]
        if invalid_channels:
            raise HTTPException(status_code=422, detail=f"channels invalidos: {invalid_channels}")

    if idempotency_key and len(idempotency_key) > 200:
        raise HTTPException(status_code=422, detail="Idempotency-Key muito longa")
    if body.optimize_send_time:
        raise HTTPException(
            status_code=422,
            detail="Send-Time Optimization usa o endpoint assíncrono /agents/retention/enqueue.",
        )

    orchestrator = RetentionOrchestrator(
        db, tenant_id=auth.tenant_id, prefer_whatsapp_medio=body.prefer_whatsapp_medio
    )
    return await orchestrator.run(
        risk_levels=body.risk_levels,
        batch_id=body.batch_id,
        limit=body.limit,
        dry_run=body.dry_run,
        channels=body.channels,
        campaign_id=body.campaign_id,
        idempotency_key=idempotency_key,
        student_ids=body.student_ids,
    )


@router.post("/agents/retention/enqueue", status_code=202)
async def enqueue_retention(
    body: RetentionRunRequest,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    auth: AuthContext = Depends(require_min_role("operator")),
    db: AsyncSession = Depends(get_db),
):
    invalid_levels = [lvl for lvl in body.risk_levels if lvl not in _VALID_RISK_LEVELS]
    if invalid_levels:
        raise HTTPException(status_code=422, detail=f"risk_levels invalidos: {invalid_levels}")
    if body.channels:
        invalid_channels = [c for c in body.channels if c not in _VALID_CHANNELS]
        if invalid_channels:
            raise HTTPException(status_code=422, detail=f"channels invalidos: {invalid_channels}")
    if idempotency_key and len(idempotency_key) > 200:
        raise HTTPException(status_code=422, detail="Idempotency-Key muito longa")

    if not body.optimize_send_time:
        try:
            job = await enqueue_retention_job(
                tenant_id=auth.tenant_id,
                tenant_slug=auth.tenant_slug,
                payload=body.model_dump(),
                idempotency_key=idempotency_key,
            )
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Fila de retenção indisponível") from exc
        return {
            "job_id": job["id"],
            "status": job["status"],
            "deduplicated": job.get("deduplicated", False),
            "created_at": job["created_at"],
        }

    students = await fetch_eligible_students(
        db,
        tenant_id=auth.tenant_id,
        risk_levels=body.risk_levels,
        batch_id=body.batch_id,
        limit=body.limit,
        student_ids=body.student_ids,
    )
    scheduled_jobs: list[dict[str, object]] = []
    failed_scheduling: list[dict[str, str]] = []
    skipped = 0
    for student in students:
        raw_candidates = decide_channels(
            risk_level=student.risk_level or "baixo",
            telefone=student.telefone,
            email=student.email,
            prefer_whatsapp_medio=body.prefer_whatsapp_medio,
        )
        candidates = [
            channel for channel in raw_candidates
            if (not body.channels or channel in body.channels)
            and is_communication_allowed(student, channel, "retention")
        ]
        if not candidates:
            skipped += 1
            continue
        try:
            recommendation = await recommend_send_time(
                db,
                tenant_id=auth.tenant_id,
                student_id=student.id,
                channels=candidates,
            )
            scheduled_for = datetime.fromisoformat(
                recommendation["next_send_at"].replace("Z", "+00:00")
            )
            payload = body.model_dump(exclude={"optimize_send_time", "student_ids", "channels"})
            payload.update({
                "student_ids": [student.id],
                "channels": [recommendation["channel"]],
                "optimize_send_time": False,
            })
            student_key = None
            if idempotency_key:
                import hashlib
                digest = hashlib.sha256(f"{idempotency_key}:{student.id}".encode("utf-8")).hexdigest()
                student_key = f"smart-send:{digest}"
            job = await enqueue_retention_job(
                tenant_id=auth.tenant_id,
                tenant_slug=auth.tenant_slug,
                payload=payload,
                idempotency_key=student_key,
                scheduled_at=scheduled_for,
            )
            scheduled_jobs.append({
                "job_id": job["id"],
                "student_id": student.id,
                "channel": recommendation["channel"],
                "status": job["status"],
                "scheduled_for": recommendation["next_send_at"],
                "timezone": recommendation["timezone"],
                "confidence": recommendation["confidence"],
                "reason": recommendation["reason"],
                "historical_attempts_at_hour": recommendation["historical_attempts_at_hour"],
            })
        except Exception as exc:
            failed_scheduling.append({"student_id": student.id, "reason": type(exc).__name__})

    if students and not scheduled_jobs and failed_scheduling:
        raise HTTPException(status_code=503, detail="Não foi possível agendar envios otimizados.")
    return {
        "optimize_send_time": True,
        "scheduled_count": len(scheduled_jobs),
        "skipped_count": skipped,
        "failed_scheduling_count": len(failed_scheduling),
        "scheduled_jobs": scheduled_jobs,
        "failed_scheduling": failed_scheduling,
        "message": (
            "Cada aluno elegível foi programado no melhor horário observado; "
            "histórico insuficiente usa fallback local às 10h."
        ),
    }
