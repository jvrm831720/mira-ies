"""Orquestrador de retenção com envio seguro e isolamento por tenant."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import Channel, MessageContext, SendResult
from app.agents.channels.email import EmailAgent
from app.agents.channels.sms import SmsAgent
from app.agents.channels.whatsapp import WhatsAppAgent
from app.agents.rules import check_anti_spam, decide_channels, skip_reason_for_no_channel
from app.core.config import get_settings
from app.models.intervention import InterventionLog
from app.models.student import Student
from app.services.provider_guard import acquire_send_slot, record_provider_outcome

CHANNEL_AGENTS: dict[Channel, Any] = {
    "whatsapp": WhatsAppAgent(),
    "email": EmailAgent(),
    "sms": SmsAgent(),
}

VALID_RISK_LEVELS = {"baixo", "medio", "critico"}
_SUCCESS_STATUSES = ("sent", "dry_run")


def _configured_provider(channel: Channel, settings: Any) -> str:
    if channel == "whatsapp" and settings.waha_api_url and settings.waha_api_key:
        return "waha"
    if channel == "whatsapp" and settings.evolution_api_url and settings.evolution_api_key:
        return "evolution"
    if channel == "email" and settings.resend_api_key:
        return "resend"
    if channel == "sms" and settings.twilio_account_sid:
        return "twilio"
    return "dry_run"


def _message_key(execution_key: str, student_id: str, channel: str) -> str:
    raw = f"{execution_key}:{student_id}:{channel}".encode("utf-8")
    return f"mira-msg-{hashlib.sha256(raw).hexdigest()}"


def _build_context(student: Student) -> MessageContext:
    shap = student.shap_top_factors or {}
    top3 = shap.get("top_3") or []
    top_factor_label = top3[0].get("label") if top3 and isinstance(top3[0], dict) else None
    actions = shap.get("recommended_actions") or []
    recommended_action = actions[0] if actions else None
    return MessageContext(
        tenant_id=student.tenant_id,
        student_id=student.id,
        matricula=student.matricula,
        nome=student.nome,
        curso=student.curso,
        risk_level=student.risk_level or "baixo",
        risk_score=student.risk_score,
        top_factor_label=top_factor_label,
        recommended_action=recommended_action,
        telefone=student.telefone,
        email=student.email,
    )


def _log_entry(
    *,
    tenant_id: str,
    student: Student,
    channel: str | None,
    status: str,
    message: str = "",
    skip_reason: str | None = None,
    error: str | None = None,
    provider: str | None = None,
    external_id: str | None = None,
    correlation_id: str | None = None,
    idempotency_key: str | None = None,
    job_id: str | None = None,
    campaign_id: str | None = None,
    delivery_status: str | None = None,
) -> InterventionLog:
    return InterventionLog(
        tenant_id=tenant_id,
        student_id=student.id,
        matricula=student.matricula,
        channel=channel,
        risk_level=student.risk_level,
        risk_score=student.risk_score,
        template_id=f"{channel}_{student.risk_level}" if channel else None,
        message_preview=(message[:120] if message else None),
        status=status,
        skip_reason=skip_reason,
        error=error,
        provider=provider,
        external_id=external_id,
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
        job_id=job_id,
        campaign_id=campaign_id,
        delivery_status=delivery_status,
    )


async def fetch_eligible_students(
    session: AsyncSession,
    *,
    tenant_id: str,
    risk_levels: list[str],
    batch_id: str | None = None,
    limit: int = 50,
    student_ids: list[str] | None = None,
) -> list[Student]:
    levels = [lvl for lvl in risk_levels if lvl in VALID_RISK_LEVELS] or ["critico"]
    query = select(Student).where(
        Student.tenant_id == tenant_id,
        Student.risk_level.in_(levels),
        Student.is_active == True,  # noqa: E712
    )
    if batch_id:
        query = query.where(Student.batch_id == batch_id)
    if student_ids:
        query = query.where(Student.id.in_(student_ids))
    query = query.order_by(Student.risk_score.desc()).limit(limit)
    result = await session.execute(query)
    return list(result.scalars().all())


async def _last_contact_at_channel(
    session: AsyncSession,
    *,
    tenant_id: str,
    student_id: str,
    channel: str,
    since: datetime,
) -> datetime | None:
    q = (
        select(InterventionLog.created_at)
        .where(
            InterventionLog.tenant_id == tenant_id,
            InterventionLog.student_id == student_id,
            InterventionLog.channel == channel,
            InterventionLog.status.in_(_SUCCESS_STATUSES),
            InterventionLog.created_at >= since,
        )
        .order_by(InterventionLog.created_at.desc())
        .limit(1)
    )
    return (await session.execute(q)).scalar_one_or_none()


async def _contacts_last_7_days(
    session: AsyncSession, *, tenant_id: str, student_id: str, since: datetime
) -> int:
    q = select(func.count(InterventionLog.id)).where(
        InterventionLog.tenant_id == tenant_id,
        InterventionLog.student_id == student_id,
        InterventionLog.status.in_(_SUCCESS_STATUSES),
        InterventionLog.created_at >= since,
    )
    return (await session.execute(q)).scalar() or 0


async def _find_by_idempotency_key(
    session: AsyncSession, *, tenant_id: str, idempotency_key: str
) -> InterventionLog | None:
    query = select(InterventionLog).where(
        InterventionLog.tenant_id == tenant_id,
        InterventionLog.idempotency_key == idempotency_key,
    )
    return (await session.execute(query)).scalar_one_or_none()


async def _reserve_send_log(
    session: AsyncSession,
    *,
    tenant_id: str,
    student: Student,
    channel: Channel,
    message: str,
    provider: str,
    idempotency_key: str,
    job_id: str | None,
    campaign_id: str | None,
) -> tuple[InterventionLog, bool]:
    existing = await _find_by_idempotency_key(
        session, tenant_id=tenant_id, idempotency_key=idempotency_key
    )
    if existing:
        return existing, False

    log = _log_entry(
        tenant_id=tenant_id,
        student=student,
        channel=channel,
        status="sending",
        message=message,
        provider=provider,
        correlation_id=idempotency_key,
        idempotency_key=idempotency_key,
        job_id=job_id,
        campaign_id=campaign_id,
        delivery_status="queued",
    )
    session.add(log)
    try:
        await session.commit()
        await session.refresh(log)
        return log, True
    except IntegrityError:
        await session.rollback()
        existing = await _find_by_idempotency_key(
            session, tenant_id=tenant_id, idempotency_key=idempotency_key
        )
        if existing:
            return existing, False
        raise


async def _send_with_guard(
    *,
    agent: Any,
    ctx: MessageContext,
    message: str,
    dry_run: bool,
    tenant_id: str,
    channel: Channel,
    idempotency_key: str,
) -> SendResult:
    settings = get_settings()
    configured_provider = _configured_provider(channel, settings)
    if dry_run or configured_provider == "dry_run":
        return await agent.send(ctx, message, dry_run=dry_run, idempotency_key=idempotency_key)

    guard = await acquire_send_slot(
        tenant_id=tenant_id, channel=channel, provider=configured_provider
    )
    if not guard.allowed:
        return SendResult(
            ok=False,
            channel=channel,
            provider=configured_provider,
            error=guard.reason,
            outcome="unknown" if guard.ambiguous else "confirmed_failure",
            ambiguous=guard.ambiguous,
            halt_fallback=guard.halt_fallback,
        )

    result = await agent.send(
        ctx, message, dry_run=False, idempotency_key=idempotency_key
    )
    try:
        await record_provider_outcome(
            provider=configured_provider,
            success=result.ok,
            ambiguous=result.ambiguous or result.halt_fallback,
        )
    except Exception:
        pass
    return result


class RetentionOrchestrator:
    def __init__(
        self,
        session: AsyncSession,
        *,
        tenant_id: str,
        prefer_whatsapp_medio: bool = False,
    ):
        self.session = session
        self.tenant_id = tenant_id
        self.prefer_whatsapp_medio = prefer_whatsapp_medio
        self.settings = get_settings()

    async def run(
        self,
        *,
        risk_levels: list[str],
        batch_id: str | None = None,
        limit: int = 50,
        dry_run: bool | None = None,
        channels: list[str] | None = None,
        job_id: str | None = None,
        campaign_id: str | None = None,
        idempotency_key: str | None = None,
        student_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        dry_run = self.settings.agents_dry_run_default if dry_run is None else dry_run
        allowed_channels = set(channels) if channels else {"whatsapp", "email", "sms"}
        execution_key = idempotency_key or job_id or str(uuid4())

        students = await fetch_eligible_students(
            self.session,
            tenant_id=self.tenant_id,
            risk_levels=risk_levels,
            batch_id=batch_id,
            limit=limit,
            student_ids=student_ids,
        )

        by_channel: dict[str, dict[str, int]] = {}

        def _bump(key: str, status: str) -> None:
            bucket = by_channel.setdefault(
                key, {"sent": 0, "dry_run": 0, "skipped": 0, "failed": 0}
            )
            bucket[status] = bucket.get(status, 0) + 1

        for student in students:
            if student.communication_opt_out:
                self.session.add(
                    _log_entry(
                        tenant_id=self.tenant_id,
                        student=student,
                        channel=None,
                        status="skipped",
                        skip_reason="communication_opt_out",
                        delivery_status="not_applicable",
                        job_id=job_id,
                        campaign_id=campaign_id,
                    )
                )
                _bump("_none", "skipped")
                continue

            risk_level = student.risk_level or "baixo"
            candidates = [
                c
                for c in decide_channels(
                    risk_level=risk_level,
                    telefone=student.telefone,
                    email=student.email,
                    prefer_whatsapp_medio=self.prefer_whatsapp_medio,
                )
                if c in allowed_channels
            ]

            if not candidates:
                reason = skip_reason_for_no_channel(risk_level)
                self.session.add(
                    _log_entry(
                        tenant_id=self.tenant_id,
                        student=student,
                        channel=None,
                        status="skipped",
                        skip_reason=reason,
                        delivery_status="not_applicable",
                        job_id=job_id,
                        campaign_id=campaign_id,
                    )
                )
                _bump("_none", "skipped")
                continue

            ctx = _build_context(student)
            now = datetime.now(timezone.utc)
            week_ago = now - timedelta(days=7)
            contacts_week = await _contacts_last_7_days(
                self.session,
                tenant_id=self.tenant_id,
                student_id=student.id,
                since=week_ago,
            )

            for channel in candidates:
                last_contact = await _last_contact_at_channel(
                    self.session,
                    tenant_id=self.tenant_id,
                    student_id=student.id,
                    channel=channel,
                    since=week_ago,
                )
                allowed, block_reason = check_anti_spam(
                    channel=channel,
                    now=now,
                    last_contact_at_this_channel=last_contact,
                    contacts_last_7_days=contacts_week,
                    min_hours_between_contact=self.settings.agents_min_hours_between_contact,
                    max_contacts_per_week=self.settings.agents_max_contacts_per_week,
                )
                if not allowed:
                    self.session.add(
                        _log_entry(
                            tenant_id=self.tenant_id,
                            student=student,
                            channel=channel,
                            status="skipped",
                            skip_reason=block_reason,
                            delivery_status="not_applicable",
                            job_id=job_id,
                            campaign_id=campaign_id,
                        )
                    )
                    _bump(channel, "skipped")
                    continue

                agent = CHANNEL_AGENTS[channel]
                message = agent.render(ctx)
                send_key = _message_key(execution_key, student.id, channel)
                provider = _configured_provider(channel, self.settings)
                log, reserved = await _reserve_send_log(
                    self.session,
                    tenant_id=self.tenant_id,
                    student=student,
                    channel=channel,
                    message=message,
                    provider=provider,
                    idempotency_key=send_key,
                    job_id=job_id,
                    campaign_id=campaign_id,
                )

                if not reserved:
                    if log.status in _SUCCESS_STATUSES:
                        _bump(channel, log.status)
                        break
                    if log.status in {"sending", "unknown"}:
                        _bump(channel, "unknown")
                        break
                    if log.status == "failed":
                        _bump(channel, "failed")
                        continue

                result = await _send_with_guard(
                    agent=agent,
                    ctx=ctx,
                    message=message,
                    dry_run=dry_run,
                    tenant_id=self.tenant_id,
                    channel=channel,
                    idempotency_key=send_key,
                )
                status = "unknown" if result.ambiguous else ("failed" if not result.ok else ("dry_run" if result.dry_run else "sent"))
                if result.ambiguous:
                    delivery_status = "unknown"
                elif result.ok and result.dry_run:
                    delivery_status = "queued"
                elif result.ok:
                    delivery_status = "submitted"
                else:
                    delivery_status = "failed"
                log.status = status
                log.error = result.error
                log.provider = result.provider
                log.external_id = result.external_id
                log.delivery_status = delivery_status
                log.delivery_updated_at = datetime.now(timezone.utc)
                await self.session.commit()
                _bump(channel, status)

                if result.ok:
                    contacts_week += 1
                    break
                if result.ambiguous or result.halt_fallback:
                    break

        await self.session.commit()

        totals = {"sent": 0, "dry_run": 0, "skipped": 0, "failed": 0}
        for counts in by_channel.values():
            for key, value in counts.items():
                totals[key] = totals.get(key, 0) + value

        contacted = totals.get("sent", 0) + totals.get("dry_run", 0)
        return {
            "tenant_id": self.tenant_id,
            "dry_run": dry_run,
            "campaign_id": campaign_id,
            "students_evaluated": len(students),
            "by_channel": by_channel,
            "totals": totals,
            "message": (
                f"Régua processada: {contacted} contatos, "
                f"{totals.get('skipped', 0)} ignorados, {totals.get('failed', 0)} falhas."
            ),
        }


async def preview_message(
    session: AsyncSession,
    *,
    tenant_id: str,
    student_id: str,
    prefer_whatsapp_medio: bool = False,
) -> dict[str, Any] | None:
    student = await session.get(Student, student_id)
    if not student or student.tenant_id != tenant_id:
        return None

    risk_level = student.risk_level or "baixo"
    if student.communication_opt_out:
        return {
            "student_id": student.id,
            "matricula": student.matricula,
            "risk_level": risk_level,
            "channel": None,
            "message": None,
            "reason": "communication_opt_out",
        }
    candidates = decide_channels(
        risk_level=risk_level,
        telefone=student.telefone,
        email=student.email,
        prefer_whatsapp_medio=prefer_whatsapp_medio,
    )
    if not candidates:
        return {
            "student_id": student.id,
            "matricula": student.matricula,
            "risk_level": risk_level,
            "channel": None,
            "message": None,
            "reason": skip_reason_for_no_channel(risk_level),
        }

    ctx = _build_context(student)
    channel = candidates[0]
    agent = CHANNEL_AGENTS[channel]
    return {
        "student_id": student.id,
        "matricula": student.matricula,
        "risk_level": risk_level,
        "channel": channel,
        "candidates": candidates,
        "message": agent.render(ctx),
    }
