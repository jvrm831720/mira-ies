"""Rotas do sistema multiagente de retencao (orquestrador + canais WhatsApp/E-mail/SMS)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.orchestrator import RetentionOrchestrator, preview_message, fetch_eligible_students
from app.agents.rules import decide_channels
from app.core.auth import AuthContext, get_current_tenant, require_min_role
from app.core.config import get_settings
from app.db.session import get_db
from app.models.intervention import InterventionLog, ProviderCallMetric
from app.models.student import Student
from app.models.engagement import StudentEngagementEvent
from app.services.consent import is_communication_allowed
from app.services.engagement import record_engagement_event, recommend_send_time
from app.services.retention_queue import enqueue_retention_job, get_job, redis_client

router = APIRouter()

_VALID_CHANNELS = {"whatsapp", "email", "sms"}
_VALID_RISK_LEVELS = {"baixo", "medio", "critico"}
_VALID_STATUSES = {"planned", "sending", "sent", "dry_run", "unknown", "failed", "skipped"}
_VALID_OUTCOMES = {
    "responded",
    "no_response",
    "stayed",
    "dropped",
    "transferred",
    "unknown",
}


class RetentionRunRequest(BaseModel):
    batch_id: Optional[str] = None
    campaign_id: Optional[str] = Field(default=None, max_length=120)
    risk_levels: list[str] = Field(default_factory=lambda: ["critico"], max_length=3)
    limit: int = Field(default=50, ge=1, le=500)
    dry_run: Optional[bool] = None
    channels: Optional[list[str]] = Field(default=None, max_length=3)
    prefer_whatsapp_medio: bool = False
    student_ids: Optional[list[str]] = Field(default=None, max_length=500)
    optimize_send_time: bool = False


class OutcomeUpdateRequest(BaseModel):
    outcome: Literal[
        "responded", "no_response", "stayed", "dropped", "transferred", "unknown"
    ]
    note: Optional[str] = Field(default=None, max_length=240)
    source: Literal["manual", "import", "system"] = "manual"


def _serialize_log(log: InterventionLog) -> dict:
    return {
        "id": log.id,
        "student_id": log.student_id,
        "matricula": log.matricula,
        "channel": log.channel,
        "risk_level": log.risk_level,
        "risk_score": log.risk_score,
        "status": log.status,
        "skip_reason": log.skip_reason,
        "decision_reason": log.decision_reason,
        "decision_context": log.decision_context,
        "error": log.error,
        "provider": log.provider,
        "external_id": log.external_id,
        "correlation_id": log.correlation_id,
        "idempotency_key": log.idempotency_key,
        "job_id": log.job_id,
        "campaign_id": log.campaign_id,
        "delivery_status": log.delivery_status,
        "delivery_event_id": log.delivery_event_id,
        "delivery_updated_at": log.delivery_updated_at,
        "message_preview": log.message_preview,
        "outcome": log.outcome,
        "outcome_at": log.outcome_at,
        "outcome_source": log.outcome_source,
        "outcome_note": log.outcome_note,
        "created_at": log.created_at,
    }


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
        "message": "Cada aluno elegível foi programado no melhor horário observado; histórico insuficiente usa fallback local às 10h.",
    }


@router.get("/agents/retention/jobs/{job_id}")
async def retention_job_status(
    job_id: str,
    auth: AuthContext = Depends(get_current_tenant),
):
    try:
        job = await get_job(job_id, tenant_id=auth.tenant_id)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Fila de retenção indisponível") from exc
    if not job:
        raise HTTPException(status_code=404, detail="Job não encontrado")
    return job


@router.get("/agents/retention/send-time/{student_id}")
async def get_retention_send_time(
    student_id: str,
    channels: list[str] | None = Query(None),
    auth: AuthContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    if channels:
        invalid_channels = [channel for channel in channels if channel not in _VALID_CHANNELS]
        if invalid_channels:
            raise HTTPException(status_code=422, detail=f"channels inválidos: {invalid_channels}")
    result = await db.execute(
        select(Student).where(Student.id == student_id, Student.tenant_id == auth.tenant_id)
    )
    student = result.scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="Aluno não encontrado.")
    candidates = decide_channels(
        risk_level=student.risk_level or "baixo",
        telefone=student.telefone,
        email=student.email,
    )
    candidates = [
        channel for channel in candidates
        if (not channels or channel in channels)
        and is_communication_allowed(student, channel, "retention")
    ]
    if not candidates:
        raise HTTPException(status_code=422, detail="Aluno sem canal elegível para a finalidade de retenção.")
    return await recommend_send_time(
        db, tenant_id=auth.tenant_id, student_id=student.id, channels=candidates
    )


@router.get("/agents/retention/logs")
async def list_retention_logs(
    limit: int = Query(50, ge=1, le=500),
    channel: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    student_id: Optional[str] = Query(None),
    outcome: Optional[str] = Query(None),
    auth: AuthContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    if channel and channel not in _VALID_CHANNELS:
        raise HTTPException(status_code=422, detail=f"channel invalido: {channel}")
    if status and status not in _VALID_STATUSES:
        raise HTTPException(status_code=422, detail=f"status invalido: {status}")
    if outcome and outcome not in _VALID_OUTCOMES and outcome != "pending":
        raise HTTPException(status_code=422, detail=f"outcome invalido: {outcome}")

    q = select(InterventionLog).where(InterventionLog.tenant_id == auth.tenant_id)
    if channel:
        q = q.where(InterventionLog.channel == channel)
    if status:
        q = q.where(InterventionLog.status == status)
    if student_id:
        q = q.where(InterventionLog.student_id == student_id)
    if outcome == "pending":
        q = q.where(InterventionLog.outcome.is_(None))
    elif outcome:
        q = q.where(InterventionLog.outcome == outcome)
    q = q.order_by(InterventionLog.created_at.desc()).limit(limit)
    logs = (await db.execute(q)).scalars().all()
    return {"count": len(logs), "logs": [_serialize_log(log) for log in logs]}


@router.patch("/agents/retention/logs/{log_id}/outcome")
async def set_retention_outcome(
    log_id: str,
    body: OutcomeUpdateRequest,
    auth: AuthContext = Depends(require_min_role("operator")),
    db: AsyncSession = Depends(get_db),
):
    """Fecha o ciclo de aprendizado: registra o desfecho da intervenção."""
    result = await db.execute(
        select(InterventionLog).where(
            InterventionLog.id == log_id,
            InterventionLog.tenant_id == auth.tenant_id,
        )
    )
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail="Evento de retenção não encontrado")

    occurred_at = datetime.now(timezone.utc)
    log.outcome = body.outcome
    log.outcome_at = occurred_at
    log.outcome_source = body.source
    log.outcome_note = body.note
    if body.outcome in {"responded", "no_response"} and log.student_id:
        await record_engagement_event(
            db,
            tenant_id=auth.tenant_id,
            student_id=log.student_id,
            event_key=f"outcome:{log.id}:{body.outcome}:{occurred_at.isoformat()}",
            event_type="replied" if body.outcome == "responded" else "no_response",
            channel=log.channel,
            source=f"outcome_{body.source}",
            intervention_log_id=log.id,
            occurred_at=occurred_at,
            event_metadata={"outcome_source": body.source},
        )
    else:
        await db.commit()
    await db.refresh(log)
    return _serialize_log(log)


@router.get("/agents/retention/preview/{student_id}")
async def preview_retention_message(
    student_id: str,
    prefer_whatsapp_medio: bool = Query(False),
    auth: AuthContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await preview_message(
        db,
        tenant_id=auth.tenant_id,
        student_id=student_id,
        prefer_whatsapp_medio=prefer_whatsapp_medio,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Aluno nao encontrado")
    return result


@router.get("/agents/status")
async def agents_status(auth: AuthContext = Depends(get_current_tenant)):
    settings = get_settings()
    return {
        "dry_run_default": settings.agents_dry_run_default,
        "anti_spam": {
            "min_hours_between_contact": settings.agents_min_hours_between_contact,
            "max_contacts_per_week": settings.agents_max_contacts_per_week,
        },
        "providers": {
            "whatsapp": "waha" if settings.waha_api_url and settings.waha_api_key else (
                "evolution" if settings.evolution_api_url and settings.evolution_api_key else "dry_run"
            ),
            "email": "resend" if settings.resend_api_key else "dry_run",
            "sms": "twilio" if settings.twilio_account_sid else "dry_run",
        },
        "queue": {
            "name": settings.retention_queue_name,
            "dead_letter_name": settings.retention_dead_letter_queue_name,
            "max_attempts": settings.retention_max_attempts,
            "retry_backoff_seconds": settings.retention_retry_backoff_seconds,
        },
        "outcomes": sorted(_VALID_OUTCOMES),
    }


@router.get("/agents/retention/analytics")
async def retention_analytics(
    days: int = Query(30, ge=1, le=365),
    auth: AuthContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Indicadores agregados por tenant: entrega, engajamento, custo e desfecho acadêmico."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    channels = ("whatsapp", "email", "sms")
    delivered_states = {"delivered", "read", "clicked", "replied"}
    bounce_states = {"failed", "rejected", "bounced", "invalid"}
    final_outcomes = ("stayed", "dropped", "transferred")

    rows = (
        await db.execute(
            select(
                InterventionLog.channel,
                InterventionLog.status,
                InterventionLog.delivery_status,
                func.count(InterventionLog.id),
            )
            .where(
                InterventionLog.tenant_id == auth.tenant_id,
                InterventionLog.created_at >= cutoff,
                InterventionLog.channel.in_(channels),
            )
            .group_by(
                InterventionLog.channel,
                InterventionLog.status,
                InterventionLog.delivery_status,
            )
        )
    ).all()
    health = {
        channel: {
            "messages_attempted": 0,
            "messages_sent": 0,
            "delivered_messages": 0,
            "bounced_messages": 0,
            "engaged_messages": 0,
            "clicked_messages": 0,
            "replied_messages": 0,
            "failed_messages": 0,
            "unknown_messages": 0,
        }
        for channel in channels
    }
    for channel, status, delivery_status, count in rows:
        if channel not in health:
            continue
        metric = health[channel]
        if status in {"sent", "failed", "unknown", "sending"}:
            metric["messages_attempted"] += int(count)
        if status == "sent":
            metric["messages_sent"] += int(count)
        elif status == "failed":
            metric["failed_messages"] += int(count)
        elif status == "unknown":
            metric["unknown_messages"] += int(count)
        if delivery_status in delivered_states:
            metric["delivered_messages"] += int(count)
        if delivery_status in bounce_states:
            metric["bounced_messages"] += int(count)
        if delivery_status in {"read", "clicked", "replied"}:
            metric["engaged_messages"] += int(count)
        if delivery_status == "clicked":
            metric["clicked_messages"] += int(count)
        if delivery_status == "replied":
            metric["replied_messages"] += int(count)

    contact_rows = (
        await db.execute(
            select(InterventionLog.channel, func.count(func.distinct(InterventionLog.student_id)))
            .where(
                InterventionLog.tenant_id == auth.tenant_id,
                InterventionLog.created_at >= cutoff,
                InterventionLog.status == "sent",
                InterventionLog.channel.in_(channels),
                InterventionLog.student_id.is_not(None),
            )
            .group_by(InterventionLog.channel)
        )
    ).all()
    unique_contacts = {channel: int(count) for channel, count in contact_rows}

    outcome_rows = (
        await db.execute(
            select(
                InterventionLog.channel,
                InterventionLog.outcome,
                func.count(func.distinct(InterventionLog.student_id)),
            )
            .where(
                InterventionLog.tenant_id == auth.tenant_id,
                InterventionLog.created_at >= cutoff,
                InterventionLog.status == "sent",
                InterventionLog.channel.in_(channels),
                InterventionLog.student_id.is_not(None),
                InterventionLog.outcome.in_(final_outcomes),
            )
            .group_by(InterventionLog.channel, InterventionLog.outcome)
        )
    ).all()
    outcomes_by_channel = {
        channel: {"stayed": 0, "dropped": 0, "transferred": 0}
        for channel in channels
    }
    for channel, outcome, count in outcome_rows:
        if channel in outcomes_by_channel and outcome in outcomes_by_channel[channel]:
            outcomes_by_channel[channel][outcome] = int(count)

    attributed_rows = (
        await db.execute(
            select(InterventionLog.channel, func.count(func.distinct(InterventionLog.student_id)))
            .where(
                InterventionLog.tenant_id == auth.tenant_id,
                InterventionLog.created_at >= cutoff,
                InterventionLog.status == "sent",
                InterventionLog.channel.in_(channels),
                InterventionLog.student_id.is_not(None),
                InterventionLog.outcome.in_(final_outcomes),
            )
            .group_by(InterventionLog.channel)
        )
    ).all()
    attributed_contacts = {channel: int(count) for channel, count in attributed_rows}

    settings = get_settings()
    cost_rates = {
        "whatsapp": settings.agents_cost_per_whatsapp_message_brl,
        "email": settings.agents_cost_per_email_message_brl,
        "sms": settings.agents_cost_per_sms_message_brl,
    }
    per_channel = {}
    total_sent = 0
    estimated_cost_total = 0.0
    cost_configured_channels = 0
    for channel in channels:
        metric = health[channel]
        sent = metric["messages_sent"]
        delivered = metric["delivered_messages"]
        bounced = metric["bounced_messages"]
        retained = outcomes_by_channel[channel]["stayed"]
        attributed = attributed_contacts.get(channel, 0)
        contacted = unique_contacts.get(channel, 0)
        unit_cost = cost_rates[channel]
        total_cost = round(sent * unit_cost, 2) if unit_cost > 0 else None
        if unit_cost > 0:
            estimated_cost_total += total_cost or 0.0
            cost_configured_channels += 1
        metric.update({
            "unique_students_contacted": contacted,
            "delivery_rate_pct": round(delivered / sent * 100, 1) if sent else None,
            "bounce_rate_pct": round(bounced / sent * 100, 1) if sent else None,
            "engagement_rate_pct": round(metric["engaged_messages"] / sent * 100, 1) if sent else None,
            "estimated_cost_brl_per_send": round(unit_cost, 4) if unit_cost > 0 else None,
            "estimated_cost_brl_total": total_cost,
        })
        per_channel[channel] = {
            **metric,
            "attribution": {
                "attributed_students": attributed,
                "retained_students": retained,
                "dropped_students": outcomes_by_channel[channel]["dropped"],
                "transferred_students": outcomes_by_channel[channel]["transferred"],
                "retention_rate_pct": round(retained / attributed * 100, 1) if attributed else None,
                "attribution_coverage_pct": round(attributed / contacted * 100, 1) if contacted else None,
            },
        }
        total_sent += sent

    overall_contacts = (
        await db.execute(
            select(func.count(func.distinct(InterventionLog.student_id))).where(
                InterventionLog.tenant_id == auth.tenant_id,
                InterventionLog.created_at >= cutoff,
                InterventionLog.status == "sent",
                InterventionLog.student_id.is_not(None),
            )
        )
    ).scalar_one()
    overall_attributed = (
        await db.execute(
            select(func.count(func.distinct(InterventionLog.student_id))).where(
                InterventionLog.tenant_id == auth.tenant_id,
                InterventionLog.created_at >= cutoff,
                InterventionLog.status == "sent",
                InterventionLog.student_id.is_not(None),
                InterventionLog.outcome.in_(final_outcomes),
            )
        )
    ).scalar_one()
    overall_retained = (
        await db.execute(
            select(func.count(func.distinct(InterventionLog.student_id))).where(
                InterventionLog.tenant_id == auth.tenant_id,
                InterventionLog.created_at >= cutoff,
                InterventionLog.status == "sent",
                InterventionLog.student_id.is_not(None),
                InterventionLog.outcome == "stayed",
            )
        )
    ).scalar_one()

    provider_rows = (
        await db.execute(
            select(
                ProviderCallMetric.channel,
                ProviderCallMetric.provider,
                func.count(ProviderCallMetric.id),
                func.avg(ProviderCallMetric.latency_ms),
                func.sum(case((ProviderCallMetric.succeeded.is_(True), 1), else_=0)),
            )
            .where(
                ProviderCallMetric.tenant_id == auth.tenant_id,
                ProviderCallMetric.occurred_at >= cutoff,
                ProviderCallMetric.channel.in_(channels),
            )
            .group_by(ProviderCallMetric.channel, ProviderCallMetric.provider)
        )
    ).all()
    providers = []
    latency_totals: dict[str, list[float]] = {channel: [0.0, 0.0] for channel in channels}
    for channel, provider, attempts, average_latency, successes in provider_rows:
        attempt_count = int(attempts or 0)
        success_count = int(successes or 0)
        latency = round(float(average_latency), 1) if average_latency is not None else None
        providers.append({
            "channel": channel,
            "provider": provider,
            "attempts": attempt_count,
            "successes": success_count,
            "failures": attempt_count - success_count,
            "success_rate_pct": round(success_count / attempt_count * 100, 1) if attempt_count else None,
            "average_latency_ms": latency,
        })
        if average_latency is not None and channel in latency_totals:
            latency_totals[channel][0] += float(average_latency) * attempt_count
            latency_totals[channel][1] += attempt_count
    for channel in channels:
        weighted_sum, attempt_count = latency_totals[channel]
        health[channel]["average_latency_ms"] = round(weighted_sum / attempt_count, 1) if attempt_count else None

    event_rows = (
        await db.execute(
            select(StudentEngagementEvent.event_type, func.count(StudentEngagementEvent.id))
            .where(
                StudentEngagementEvent.tenant_id == auth.tenant_id,
                StudentEngagementEvent.occurred_at >= cutoff,
            )
            .group_by(StudentEngagementEvent.event_type)
        )
    ).all()
    engagement_events = {event_type: int(count) for event_type, count in event_rows}

    return {
        "period_days": days,
        "period_start": cutoff.isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "messages_sent": total_sent,
            "unique_students_contacted": int(overall_contacts or 0),
            "attributed_students": int(overall_attributed or 0),
            "retained_students": int(overall_retained or 0),
            "retention_rate_pct": round(float(overall_retained) / float(overall_attributed) * 100, 1) if overall_attributed else None,
            "attribution_coverage_pct": round(float(overall_attributed) / float(overall_contacts) * 100, 1) if overall_contacts else None,
            "estimated_cost_brl_total": round(estimated_cost_total, 2) if cost_configured_channels else None,
            "cost_configured_channels": cost_configured_channels,
        },
        "channels": per_channel,
        "providers": providers,
        "engagement_events": engagement_events,
        "attribution_note": "Associação observacional entre status acadêmico importado e envios nos 90 dias anteriores; não demonstra causalidade.",
        "cost_note": "Custos BRL são estimados somente para canais com custo unitário configurado.",
    }


@router.get("/agents/retention/dead-letter")
async def list_retention_dead_letters(
    limit: int = Query(50, ge=1, le=500),
    auth: AuthContext = Depends(require_min_role("coordinator")),
):
    redis = redis_client()
    try:
        job_ids = await redis.lrange(get_settings().retention_dead_letter_queue_name, -limit, -1)
        jobs = []
        for job_id in reversed(job_ids):
            job = await get_job(job_id, tenant_id=auth.tenant_id, redis=redis)
            if job:
                jobs.append(job)
        return {"count": len(jobs), "jobs": jobs}
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Fila dead-letter indisponível") from exc
    finally:
        await redis.aclose()
