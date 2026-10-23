"""Regras e trilha de auditoria para preferências de comunicação por canal/finalidade."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consent import ConsentAuditEvent
from app.models.student import Student

CHANNELS = ("whatsapp", "email", "sms")
TOPICS = ("academic", "retention", "promotional")
DEFAULT_COMMUNICATION_PREFERENCES: dict[str, dict[str, bool]] = {
    # Mantém o comportamento operacional legado para canais e retenção; promocional
    # permanece desabilitado até escolha explícita.
    "channels": {"whatsapp": True, "email": True, "sms": True},
    "topics": {"academic": True, "retention": True, "promotional": False},
}


def effective_preferences(student: Student) -> dict[str, dict[str, bool]]:
    """Mescla valores persistidos com defaults estáveis para registros legados."""
    raw = student.communication_preferences or {}
    result = deepcopy(DEFAULT_COMMUNICATION_PREFERENCES)
    if not isinstance(raw, dict):
        return result
    for group, allowed in (("channels", CHANNELS), ("topics", TOPICS)):
        source = raw.get(group)
        if isinstance(source, dict):
            for key in allowed:
                value = source.get(key)
                if isinstance(value, bool):
                    result[group][key] = value
    return result


def is_communication_allowed(student: Student, channel: str, topic: str = "retention") -> bool:
    """Global opt-out sempre vence; depois são verificadas permissão do canal e finalidade."""
    if student.communication_opt_out:
        return False
    if channel not in CHANNELS or topic not in TOPICS:
        return False
    preferences = effective_preferences(student)
    return preferences["channels"][channel] and preferences["topics"][topic]


def _append_event(
    session: AsyncSession,
    *,
    tenant_id: str,
    student: Student,
    event_type: str,
    previous_value: Any,
    new_value: Any,
    source: str,
    method: str,
    location: str,
    channel: str | None = None,
    topic: str | None = None,
    source_reference: str | None = None,
    actor_user_id: str | None = None,
    occurred_at: datetime | None = None,
    notes: str | None = None,
) -> None:
    session.add(
        ConsentAuditEvent(
            tenant_id=tenant_id,
            student_id=student.id,
            student_matricula=student.matricula,
            event_type=event_type,
            channel=channel,
            topic=topic,
            previous_value=previous_value,
            new_value=new_value,
            source=(source or "system")[:40],
            method=(method or "system")[:60],
            location=(location or "unknown")[:120],
            source_reference=source_reference[:160] if source_reference else None,
            actor_user_id=actor_user_id,
            occurred_at=occurred_at or datetime.now(timezone.utc),
            notes=notes[:500] if notes else None,
        )
    )


def apply_preference_changes(
    session: AsyncSession,
    *,
    tenant_id: str,
    student: Student,
    opt_out: bool | None = None,
    channels: dict[str, bool] | None = None,
    topics: dict[str, bool] | None = None,
    source: str,
    method: str,
    location: str,
    source_reference: str | None = None,
    actor_user_id: str | None = None,
    occurred_at: datetime | None = None,
) -> int:
    """Aplica alterações explícitas e registra um evento por valor efetivamente alterado."""
    channels = channels or {}
    topics = topics or {}
    unknown_channels = set(channels) - set(CHANNELS)
    unknown_topics = set(topics) - set(TOPICS)
    if unknown_channels:
        raise ValueError(f"Canais inválidos: {', '.join(sorted(unknown_channels))}")
    if unknown_topics:
        raise ValueError(f"Finalidades inválidas: {', '.join(sorted(unknown_topics))}")
    if opt_out is None and not channels and not topics:
        raise ValueError("Informe ao menos uma preferência para alterar.")

    events = 0
    now = occurred_at or datetime.now(timezone.utc)
    if opt_out is not None:
        previous = bool(student.communication_opt_out)
        if previous != opt_out:
            student.communication_opt_out = opt_out
            student.communication_opted_out_at = now if opt_out else None
            _append_event(
                session,
                tenant_id=tenant_id,
                student=student,
                event_type="global_opt_out_enabled" if opt_out else "global_opt_out_disabled",
                previous_value=previous,
                new_value=opt_out,
                source=source,
                method=method,
                location=location,
                source_reference=source_reference,
                actor_user_id=actor_user_id,
                occurred_at=now,
            )
            events += 1

    preferences = effective_preferences(student)
    for channel, value in channels.items():
        previous = preferences["channels"][channel]
        if previous == value:
            continue
        preferences["channels"][channel] = value
        _append_event(
            session,
            tenant_id=tenant_id,
            student=student,
            event_type="channel_preference_changed",
            channel=channel,
            previous_value=previous,
            new_value=value,
            source=source,
            method=method,
            location=location,
            source_reference=source_reference,
            actor_user_id=actor_user_id,
            occurred_at=now,
        )
        events += 1

    for topic, value in topics.items():
        previous = preferences["topics"][topic]
        if previous == value:
            continue
        preferences["topics"][topic] = value
        _append_event(
            session,
            tenant_id=tenant_id,
            student=student,
            event_type="topic_preference_changed",
            topic=topic,
            previous_value=previous,
            new_value=value,
            source=source,
            method=method,
            location=location,
            source_reference=source_reference,
            actor_user_id=actor_user_id,
            occurred_at=now,
        )
        events += 1

    student.communication_preferences = preferences
    return events


def record_initial_global_opt_out(
    session: AsyncSession,
    *,
    tenant_id: str,
    student: Student,
    opt_out: bool,
    source: str,
    method: str,
    location: str,
    source_reference: str | None = None,
) -> None:
    """Registra um opt-out afirmativo informado na criação/importação de um registro."""
    if not opt_out:
        return
    _append_event(
        session,
        tenant_id=tenant_id,
        student=student,
        event_type="global_opt_out_enabled",
        previous_value=None,
        new_value=True,
        source=source,
        method=method,
        location=location,
        source_reference=source_reference,
    )
