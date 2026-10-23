"""Orquestrador de retenção com envio seguro e isolamento por tenant."""

from __future__ import annotations

import hashlib
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import Channel, MessageContext, SendResult
from app.agents.campaign_templates import render_campaign_template
from app.agents.channels.email import EmailAgent, is_valid_email
from app.agents.channels.sms import SmsAgent
from app.agents.channels.whatsapp import WhatsAppAgent, normalize_phone_br
from app.agents.rules import check_anti_spam, decide_channels, skip_reason_for_no_channel
from app.core.config import get_settings
from app.models.intervention import InterventionLog, ProviderCallMetric
from app.models.student import Student
from app.services.provider_guard import (
    acquire_send_slot,
    claim_message_send,
    finish_message_send,
    record_provider_outcome,
)
from app.agents.providers.errors import is_retryable_provider_error
from app.services.consent import effective_preferences, is_communication_allowed
from app.services.engagement import is_sms_suppressed_by_recent_engagement

logger = logging.getLogger(__name__)

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


def _configured_providers(channel: Channel, settings: Any) -> list[str]:
    """Lista providers utilizáveis na ordem definida, sem duplicar fallback entre canais."""
    if channel == "whatsapp":
        available = {
            "waha": bool(settings.waha_api_url and settings.waha_api_key),
            "evolution": bool(settings.evolution_api_url and settings.evolution_api_key),
        }
        configured_order = [
            name.strip().lower()
            for name in settings.whatsapp_provider_order.split(",")
            if name.strip()
        ]
        providers = [name for name in configured_order if available.get(name)]
        providers.extend(name for name, enabled in available.items() if enabled and name not in providers)
        return providers or ["dry_run"]
    if channel == "email" and settings.resend_api_key:
        return ["resend"]
    if channel == "sms" and settings.twilio_account_sid:
        return ["twilio"]
    return ["dry_run"]


def _provider_guard_can_failover(reason: str | None) -> bool:
    if not reason:
        return False
    lowered = reason.lower()
    return (
        "circuit breaker aberto para" in lowered
        or "rate limit de provider excedido" in lowered
        or "backpressure adaptativo" in lowered
    )


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
        behavior_properties=getattr(student, "behavior_properties", None) or {},
        engagement_score=getattr(student, "engagement_score", None),
    )


def _decision_context(student: Student, *, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    ctx = {
        "risk_level": student.risk_level,
        "risk_score": student.risk_score,
        "has_phone": bool(student.telefone),
        "has_email": bool(student.email),
        "opt_out": bool(getattr(student, "communication_opt_out", False)),
        "engagement_score": getattr(student, "engagement_score", None),
        "dynamic_risk_adjustment": getattr(student, "dynamic_risk_adjustment", 0.0),
    }
    if extra:
        ctx.update(extra)
    return ctx


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
    template_id: str | None = None,
    delivery_status: str | None = None,
    decision_reason: str | None = None,
    decision_context: dict[str, Any] | None = None,
) -> InterventionLog:
    return InterventionLog(
        tenant_id=tenant_id,
        student_id=student.id,
        matricula=student.matricula,
        channel=channel,
        risk_level=student.risk_level,
        risk_score=student.risk_score,
        template_id=(
            template_id if template_id is not None
            else f"{channel}_{student.risk_level}" if channel else None
        ),
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
        decision_reason=decision_reason,
        decision_context=decision_context or _decision_context(student),
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
    template_id: str | None,
    decision_reason: str,
    decision_context: dict[str, Any],
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
        template_id=template_id,
        delivery_status="queued",
        decision_reason=decision_reason,
        decision_context=decision_context,
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
    email_subject: str | None = None,
) -> SendResult:
    settings = get_settings()
    providers = _configured_providers(channel, settings)
    send_kwargs: dict[str, Any] = {
        "dry_run": dry_run,
        "idempotency_key": idempotency_key,
    }
    if channel == "email" and email_subject is not None:
        send_kwargs["subject_override"] = email_subject
    if dry_run or providers == ["dry_run"]:
        return await agent.send(ctx, message, **send_kwargs)

    # Verifica o provedor antes de reservar a chave: circuitos abertos não devem
    # consumir a idempotência se outro provedor ainda puder assumir o canal.
    claim_acquired = False
    uncertain_provider_failure = False
    provider_attempts: list[dict[str, Any]] = []
    final_result: SendResult | None = None
    for index, provider in enumerate(providers):
        guard = await acquire_send_slot(
            tenant_id=tenant_id, channel=channel, provider=provider
        )
        if not guard.allowed:
            final_result = SendResult(
                ok=False,
                channel=channel,
                provider=provider,
                error=guard.reason,
                outcome="unknown" if guard.ambiguous else "confirmed_failure",
                ambiguous=guard.ambiguous,
                halt_fallback=guard.halt_fallback,
            )
            if (
                channel == "whatsapp"
                and index + 1 < len(providers)
                and _provider_guard_can_failover(guard.reason)
            ):
                continue
            break

        if not claim_acquired:
            try:
                claim_acquired = await claim_message_send(
                    tenant_id=tenant_id,
                    idempotency_key=idempotency_key,
                    ttl_seconds=settings.agents_idempotency_ttl_seconds,
                )
            except Exception:
                return SendResult(
                    ok=False,
                    channel=channel,
                    provider=provider,
                    error="proteção de idempotência indisponível (Redis)",
                    outcome="unknown",
                    ambiguous=True,
                    halt_fallback=True,
                )
            if not claim_acquired:
                return SendResult(
                    ok=False,
                    channel=channel,
                    provider=provider,
                    error="chave de idempotência já reservada por outro worker",
                    outcome="unknown",
                    ambiguous=True,
                    halt_fallback=True,
                )

        provider_kwargs = dict(send_kwargs)
        if channel == "whatsapp":
            provider_kwargs["provider_override"] = provider

        started = time.monotonic()
        result = await agent.send(ctx, message, **provider_kwargs)
        elapsed = time.monotonic() - started
        provider_attempts.append({
            "provider": provider,
            "latency_ms": round(elapsed * 1000.0, 1),
            "succeeded": bool(result.ok),
            "outcome": result.outcome,
        })
        try:
            await record_provider_outcome(
                provider=provider,
                success=result.ok,
                ambiguous=result.ambiguous or result.halt_fallback,
                latency_seconds=elapsed,
            )
        except Exception:
            # O erro de telemetria não deve mascarar o resultado do envio.
            pass

        if result.ok:
            final_result = result
            break

        final_result = result
        retryable = is_retryable_provider_error(result.error)
        if retryable and result.ambiguous:
            uncertain_provider_failure = True
        if (
            channel == "whatsapp"
            and index + 1 < len(providers)
            and retryable
        ):
            logger.warning(
                "WhatsApp provider failover after retryable HTTP response",
                extra={"event_name": "provider_failover", "channel": channel,
                       "from_provider": provider, "to_provider": providers[index + 1]},
            )
            continue
        break

    if final_result is None:
        final_result = SendResult(
            ok=False, channel=channel, provider=providers[0],
            error="nenhum provider de envio disponível",
            outcome="confirmed_failure",
        )

    if uncertain_provider_failure and not final_result.ok:
        # Um secundário com falha definitiva não apaga a incerteza do 5xx primário.
        final_result.ambiguous = True
        final_result.outcome = "unknown"
        final_result.halt_fallback = True
    final_result.provider_attempts = provider_attempts

    if claim_acquired:
        try:
            if final_result.ok:
                await finish_message_send(
                    tenant_id=tenant_id, idempotency_key=idempotency_key, state="sent"
                )
            elif final_result.ambiguous or final_result.halt_fallback:
                # Resultado incerto: preservar a trava evita duplicar uma mensagem
                # que pode já ter sido aceita pelo provedor.
                await finish_message_send(
                    tenant_id=tenant_id, idempotency_key=idempotency_key, state="unknown"
                )
            else:
                await finish_message_send(
                    tenant_id=tenant_id, idempotency_key=idempotency_key, state="failed"
                )
        except Exception:
            # A chave inicial já tem TTL; falha ao gravar estado não a libera.
            pass
    return final_result

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
        campaign_actions: dict[str, dict[str, Any]] | None = None,
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
            campaign_action = (
                campaign_actions.get(student.id) if campaign_actions is not None else None
            )
            if campaign_actions is not None and campaign_action is None:
                continue

            campaign_audit: dict[str, Any] = {}
            if campaign_action is not None:
                selected_rule = {
                    "rule_id": campaign_action["rule_id"],
                    "rule_version": campaign_action["rule_version"],
                    "priority": campaign_action["priority"],
                    "channel": campaign_action["channel"],
                    "template_id": campaign_action["template_id"],
                }
                campaign_audit = {
                    "campaign_version": campaign_action["campaign_version"],
                    "selected_rule": selected_rule,
                    "evaluated_rules": campaign_action["evaluated_rules"],
                    "days_since_contact": campaign_action["days_since_contact"],
                    "template_id": campaign_action["template_id"],
                }

            if student.communication_opt_out:
                self.session.add(
                    _log_entry(
                        tenant_id=self.tenant_id,
                        student=student,
                        channel=None,
                        status="skipped",
                        skip_reason="communication_opt_out",
                        decision_reason="Aluno com opt-out de comunicação",
                        decision_context=_decision_context(student, extra=campaign_audit),
                        delivery_status="not_applicable",
                        job_id=job_id,
                        campaign_id=campaign_id,
                        template_id=campaign_action.get("template_id") if campaign_action else None,
                    )
                )
                _bump("_none", "skipped")
                continue

            risk_level = student.risk_level or "baixo"
            topic = campaign_action.get("topic", "retention") if campaign_action else "retention"
            preference_blocked = False
            if campaign_action is not None:
                requested_channel = campaign_action["channel"]
                if requested_channel not in allowed_channels:
                    raise ValueError(
                        f"Canal {requested_channel!r} não está liberado para a execução da campanha."
                    )
                has_requested_contact = (
                    is_valid_email(student.email)
                    if requested_channel == "email"
                    else bool(normalize_phone_br(student.telefone))
                )
                preference_blocked = has_requested_contact and not is_communication_allowed(
                    student, requested_channel, topic
                )
                candidates = (
                    [requested_channel]
                    if has_requested_contact and not preference_blocked
                    else []
                )
            else:
                raw_candidates = [
                    c
                    for c in decide_channels(
                        risk_level=risk_level,
                        telefone=student.telefone,
                        email=student.email,
                        prefer_whatsapp_medio=self.prefer_whatsapp_medio,
                    )
                    if c in allowed_channels
                ]
                candidates = [
                    channel for channel in raw_candidates
                    if is_communication_allowed(student, channel, topic)
                ]
                preference_blocked = bool(raw_candidates) and not candidates

            sms_suppressed_by_engagement = False
            if "sms" in candidates:
                sms_suppressed_by_engagement = await is_sms_suppressed_by_recent_engagement(
                    self.session, tenant_id=self.tenant_id, student_id=student.id,
                )
                if sms_suppressed_by_engagement:
                    candidates = [channel for channel in candidates if channel != "sms"]

            if not candidates:
                if preference_blocked:
                    reason = "communication_preference_blocked"
                elif sms_suppressed_by_engagement:
                    reason = "recent_engagement_suppression"
                elif campaign_action is not None:
                    reason = (
                        "missing_email" if campaign_action["channel"] == "email"
                        else "missing_phone"
                    )
                else:
                    reason = skip_reason_for_no_channel(risk_level)
                self.session.add(
                    _log_entry(
                        tenant_id=self.tenant_id,
                        student=student,
                        channel=None,
                        status="skipped",
                        skip_reason=reason,
                        decision_reason=f"Sem canal viável ({reason})",
                        decision_context=_decision_context(
                            student,
                            extra={
                                "candidates": [],
                                "allowed_channels": list(allowed_channels),
                                **campaign_audit,
                                "blocked_reason": reason,
                                "topic": topic,
                                "effective_preferences": effective_preferences(student),
                            },
                        ),
                        delivery_status="not_applicable",
                        job_id=job_id,
                        campaign_id=campaign_id,
                        template_id=campaign_action.get("template_id") if campaign_action else None,
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
                            decision_reason=f"Anti-spam bloqueou {channel}: {block_reason}",
                            decision_context=_decision_context(
                                student,
                                extra={
                                    "channel": channel,
                                    "contacts_week": contacts_week,
                                    "candidates": candidates,
                                    **campaign_audit,
                                },
                            ),
                            delivery_status="not_applicable",
                            job_id=job_id,
                            campaign_id=campaign_id,
                            template_id=campaign_action.get("template_id") if campaign_action else None,
                        )
                    )
                    _bump(channel, "skipped")
                    continue

                agent = CHANNEL_AGENTS[channel]
                email_subject = None
                if campaign_action is not None:
                    rendered = render_campaign_template(
                        ctx, channel, campaign_action["template_id"]
                    )
                    message = rendered.body
                    email_subject = rendered.subject
                    selected_rule = campaign_audit["selected_rule"]
                    decision_reason = (
                        f"Campanha {campaign_id} v{campaign_action['campaign_version']}; "
                        f"regra {selected_rule['rule_id']} v{selected_rule['rule_version']} "
                        f"priority={selected_rule['priority']}; canal={channel}; "
                        f"template={campaign_action['template_id']}; score={student.risk_score}"
                    )
                else:
                    message = agent.render(ctx)
                    decision_reason = (
                        f"Risco {risk_level}; canal {channel}; "
                        f"score={student.risk_score}; candidatos={candidates}"
                    )
                send_key = _message_key(execution_key, student.id, channel)
                provider = _configured_provider(channel, self.settings)
                dctx = _decision_context(
                    student,
                    extra={
                        "channel": channel,
                        "candidates": candidates,
                        "contacts_week": contacts_week,
                        "provider": provider,
                        "topic": topic,
                        "effective_preferences": effective_preferences(student),
                        **campaign_audit,
                        **({"email_subject": email_subject} if email_subject else {}),
                    },
                )
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
                    template_id=campaign_action.get("template_id") if campaign_action else None,
                    decision_reason=decision_reason,
                    decision_context=dctx,
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
                    email_subject=email_subject,
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
                for attempt_metric in result.provider_attempts:
                    self.session.add(
                        ProviderCallMetric(
                            tenant_id=self.tenant_id,
                            intervention_log_id=log.id,
                            channel=channel,
                            provider=str(attempt_metric["provider"]),
                            latency_ms=float(attempt_metric["latency_ms"]),
                            succeeded=bool(attempt_metric["succeeded"]),
                            provider_outcome=str(attempt_metric["outcome"]),
                            occurred_at=log.delivery_updated_at,
                        )
                    )
                if not log.decision_reason:
                    log.decision_reason = decision_reason
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
            "decision_reason": "Aluno com opt-out de comunicação",
        }
    raw_candidates = decide_channels(
        risk_level=risk_level,
        telefone=student.telefone,
        email=student.email,
        prefer_whatsapp_medio=prefer_whatsapp_medio,
    )
    candidates = [
        channel for channel in raw_candidates
        if is_communication_allowed(student, channel, "retention")
    ]
    if not candidates:
        reason = (
            "communication_preference_blocked"
            if raw_candidates
            else skip_reason_for_no_channel(risk_level)
        )
        return {
            "student_id": student.id,
            "matricula": student.matricula,
            "risk_level": risk_level,
            "channel": None,
            "message": None,
            "reason": reason,
            "decision_reason": f"Sem canal viável ({reason})",
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
        "decision_reason": f"Risco {risk_level}; canal preferido {channel}",
    }
