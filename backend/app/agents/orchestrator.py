"""Orquestrador de retencao: busca alunos elegiveis, decide canal, aplica anti-spam,
delega ao agente de canal e persiste InterventionLog. Sempre isolado por tenant_id.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import Channel, MessageContext
from app.agents.channels.email import EmailAgent
from app.agents.channels.sms import SmsAgent
from app.agents.channels.whatsapp import WhatsAppAgent
from app.agents.rules import check_anti_spam, decide_channels, skip_reason_for_no_channel
from app.core.config import get_settings
from app.models.intervention import InterventionLog
from app.models.student import Student

CHANNEL_AGENTS: dict[Channel, Any] = {
    "whatsapp": WhatsAppAgent(),
    "email": EmailAgent(),
    "sms": SmsAgent(),
}

VALID_RISK_LEVELS = {"baixo", "medio", "critico"}
_SUCCESS_STATUSES = ("sent", "dry_run")


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
    *, tenant_id: str, student: Student, channel: str | None, status: str,
    message: str = "", skip_reason: str | None = None, error: str | None = None,
    provider: str | None = None, external_id: str | None = None,
) -> InterventionLog:
    return InterventionLog(
        tenant_id=tenant_id, student_id=student.id, matricula=student.matricula,
        channel=channel, risk_level=student.risk_level, risk_score=student.risk_score,
        template_id=f"{channel}_{student.risk_level}" if channel else None,
        message_preview=(message[:120] if message else None),
        status=status, skip_reason=skip_reason, error=error, provider=provider, external_id=external_id,
    )


async def fetch_eligible_students(
    session: AsyncSession, *, tenant_id: str, risk_levels: list[str], batch_id: str | None = None, limit: int = 50,
) -> list[Student]:
    levels = [lvl for lvl in risk_levels if lvl in VALID_RISK_LEVELS] or ["critico"]
    query = select(Student).where(
        Student.tenant_id == tenant_id, Student.risk_level.in_(levels), Student.is_active == True,  # noqa: E712
    )
    if batch_id:
        query = query.where(Student.batch_id == batch_id)
    query = query.order_by(Student.risk_score.desc()).limit(limit)
    result = await session.execute(query)
    return list(result.scalars().all())


async def _last_contact_at_channel(
    session: AsyncSession, *, tenant_id: str, student_id: str, channel: str, since: datetime,
) -> datetime | None:
    q = (
        select(InterventionLog.created_at)
        .where(
            InterventionLog.tenant_id == tenant_id, InterventionLog.student_id == student_id,
            InterventionLog.channel == channel, InterventionLog.status.in_(_SUCCESS_STATUSES),
            InterventionLog.created_at >= since,
        )
        .order_by(InterventionLog.created_at.desc())
        .limit(1)
    )
    return (await session.execute(q)).scalar_one_or_none()


async def _contacts_last_7_days(session: AsyncSession, *, tenant_id: str, student_id: str, since: datetime) -> int:
    q = select(func.count(InterventionLog.id)).where(
        InterventionLog.tenant_id == tenant_id, InterventionLog.student_id == student_id,
        InterventionLog.status.in_(_SUCCESS_STATUSES), InterventionLog.created_at >= since,
    )
    return (await session.execute(q)).scalar() or 0


class RetentionOrchestrator:
    def __init__(self, session: AsyncSession, *, tenant_id: str, prefer_whatsapp_medio: bool = False):
        self.session = session
        self.tenant_id = tenant_id
        self.prefer_whatsapp_medio = prefer_whatsapp_medio
        self.settings = get_settings()

    async def run(
        self, *, risk_levels: list[str], batch_id: str | None = None, limit: int = 50,
        dry_run: bool | None = None, channels: list[str] | None = None,
    ) -> dict[str, Any]:
        dry_run = self.settings.agents_dry_run_default if dry_run is None else dry_run
        allowed_channels = set(channels) if channels else {"whatsapp", "email", "sms"}

        students = await fetch_eligible_students(
            self.session, tenant_id=self.tenant_id, risk_levels=risk_levels, batch_id=batch_id, limit=limit,
        )

        by_channel: dict[str, dict[str, int]] = {}

        def _bump(key: str, status: str) -> None:
            bucket = by_channel.setdefault(key, {"sent": 0, "dry_run": 0, "skipped": 0, "failed": 0})
            bucket[status] = bucket.get(status, 0) + 1

        for student in students:
            risk_level = student.risk_level or "baixo"
            candidates = [
                c for c in decide_channels(
                    risk_level=risk_level, telefone=student.telefone, email=student.email,
                    prefer_whatsapp_medio=self.prefer_whatsapp_medio,
                ) if c in allowed_channels
            ]

            if not candidates:
                reason = skip_reason_for_no_channel(risk_level)
                self.session.add(_log_entry(tenant_id=self.tenant_id, student=student, channel=None, status="skipped", skip_reason=reason))
                _bump("_none", "skipped")
                continue

            ctx = _build_context(student)
            now = datetime.now(timezone.utc)
            week_ago = now - timedelta(days=7)
            contacts_week = await _contacts_last_7_days(self.session, tenant_id=self.tenant_id, student_id=student.id, since=week_ago)

            for channel in candidates:
                last_contact = await _last_contact_at_channel(
                    self.session, tenant_id=self.tenant_id, student_id=student.id, channel=channel, since=week_ago,
                )
                allowed, block_reason = check_anti_spam(
                    channel=channel, now=now, last_contact_at_this_channel=last_contact,
                    contacts_last_7_days=contacts_week,
                    min_hours_between_contact=self.settings.agents_min_hours_between_contact,
                    max_contacts_per_week=self.settings.agents_max_contacts_per_week,
                )
                if not allowed:
                    self.session.add(_log_entry(tenant_id=self.tenant_id, student=student, channel=channel, status="skipped", skip_reason=block_reason))
                    _bump(channel, "skipped")
                    continue

                agent = CHANNEL_AGENTS[channel]
                message = agent.render(ctx)
                result = await agent.send(ctx, message, dry_run=dry_run)
                status = "failed" if not result.ok else ("dry_run" if result.dry_run else "sent")
                self.session.add(_log_entry(
                    tenant_id=self.tenant_id, student=student, channel=channel, status=status,
                    message=message, error=result.error, provider=result.provider, external_id=result.external_id,
                ))
                _bump(channel, status)

                if result.ok:
                    contacts_week += 1
                    break

        await self.session.commit()

        totals = {"sent": 0, "dry_run": 0, "skipped": 0, "failed": 0}
        for counts in by_channel.values():
            for k, v in counts.items():
                totals[k] += v

        return {
            "tenant_id": self.tenant_id, "dry_run": dry_run, "students_evaluated": len(students),
            "by_channel": by_channel, "totals": totals,
        }


async def preview_message(
    session: AsyncSession, *, tenant_id: str, student_id: str, prefer_whatsapp_medio: bool = False,
) -> dict[str, Any] | None:
    """Monta a mensagem para o canal prioritario do aluno SEM enviar nem gravar log."""
    student = await session.get(Student, student_id)
    if not student or student.tenant_id != tenant_id:
        return None

    risk_level = student.risk_level or "baixo"
    candidates = decide_channels(
        risk_level=risk_level, telefone=student.telefone, email=student.email,
        prefer_whatsapp_medio=prefer_whatsapp_medio,
    )
    if not candidates:
        return {
            "student_id": student.id, "matricula": student.matricula, "risk_level": risk_level,
            "channel": None, "message": None, "reason": skip_reason_for_no_channel(risk_level),
        }

    ctx = _build_context(student)
    channel = candidates[0]
    agent = CHANNEL_AGENTS[channel]
    return {
        "student_id": student.id, "matricula": student.matricula, "risk_level": risk_level,
        "channel": channel, "candidates": candidates, "message": agent.render(ctx),
    }
