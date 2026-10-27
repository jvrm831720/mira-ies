"""Behavioral properties, engagement scores, and per-student send-time optimization."""

from __future__ import annotations

import math
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.engagement import StudentEngagementEvent
from app.models.intervention import InterventionLog
from app.models.student import Student
from app.models.risk_assessment import RiskAssessment
from app.ml.features import build_features_from_student

STANDARD_PROPERTY_LIMITS = {
    "last_class_missed": 120,
    "current_module": 120,
    "recent_activity": 160,
}
MESSAGEABLE_STANDARD_FIELDS = {
    "last_class_missed",
    "missed_classes_this_week",
    "current_module",
    "module_progress_pct",
    "recent_activity",
    "last_activity_at",
}
_ALLOWED_EVENT_TYPES = {
    "delivered", "read", "opened", "clicked", "replied",
    "no_response", "failed", "opted_out",
}
_ENGAGEMENT_WEIGHTS = {
    "delivered": 0,
    "read": 8,
    "opened": 8,
    "clicked": 16,
    "replied": 24,
    "no_response": -12,
    "failed": -3,
    "opted_out": -18,
}
_POSITIVE_EVENTS = {"read", "opened", "clicked", "replied"}


def _clean_text(value: Any, max_length: int) -> str:
    text = str(value).strip()
    text = "".join(ch for ch in text if ch >= " " and ch not in {"\x7f"})
    return text[:max_length]


def normalize_behavior_properties(
    current: dict[str, Any] | None,
    patch: dict[str, Any],
) -> dict[str, Any]:
    """Validate structured behavioral fields and explicitly opt-in custom message fields."""
    allowed = set(STANDARD_PROPERTY_LIMITS) | {
        "missed_classes_this_week",
        "module_progress_pct",
        "last_activity_at",
        "custom_properties",
        "message_fields",
    }
    unknown = set(patch) - allowed
    if unknown:
        raise ValueError(f"Propriedades comportamentais não suportadas: {', '.join(sorted(unknown))}")

    result = dict(current or {})
    for key, limit in STANDARD_PROPERTY_LIMITS.items():
        if key not in patch:
            continue
        value = patch[key]
        result[key] = _clean_text(value, limit) if value not in (None, "") else None

    if "missed_classes_this_week" in patch:
        value = patch["missed_classes_this_week"]
        if value is None:
            result["missed_classes_this_week"] = None
        elif isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 100:
            raise ValueError("missed_classes_this_week deve ser um inteiro entre 0 e 100.")
        else:
            result["missed_classes_this_week"] = value

    if "module_progress_pct" in patch:
        value = patch["module_progress_pct"]
        if value is None:
            result["module_progress_pct"] = None
        elif isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 100:
            raise ValueError("module_progress_pct deve estar entre 0 e 100.")
        else:
            result["module_progress_pct"] = round(float(value), 1)

    if "last_activity_at" in patch:
        value = patch["last_activity_at"]
        if value is None or value == "":
            result["last_activity_at"] = None
        elif not isinstance(value, str):
            raise ValueError("last_activity_at deve ser uma data ISO-8601.")
        else:
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError("last_activity_at deve ser uma data ISO-8601 válida.") from exc
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            result["last_activity_at"] = parsed.astimezone(timezone.utc).isoformat()

    if "custom_properties" in patch:
        raw_custom = patch["custom_properties"]
        if not isinstance(raw_custom, dict) or len(raw_custom) > 30:
            raise ValueError("custom_properties deve ser um objeto com no máximo 30 propriedades.")
        custom: dict[str, str | int | float | bool | None] = dict(result.get("custom_properties") or {})
        for key, value in raw_custom.items():
            if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,39}", key):
                raise ValueError(f"Nome de propriedade customizada inválido: {key!r}")
            if any(part in key.lower() for part in ("password", "secret", "token", "api_key", "cpf", "documento", "email", "telefone", "phone", "endereco", "address", "senha", "birth", "nascimento")):
                raise ValueError(f"Propriedade customizada com nome sensível não permitida: {key!r}")
            if value is None or isinstance(value, bool):
                custom[key] = value
            elif isinstance(value, int):
                custom[key] = value
            elif isinstance(value, float) and math.isfinite(value):
                custom[key] = round(value, 4)
            elif isinstance(value, str):
                custom[key] = _clean_text(value, 80)
            else:
                raise ValueError(f"Valor não suportado para a propriedade customizada {key!r}.")
        result["custom_properties"] = custom

    if "message_fields" in patch:
        fields = patch["message_fields"]
        if not isinstance(fields, list) or len(fields) > 6:
            raise ValueError("message_fields deve conter até 6 campos.")
        custom_keys = set((result.get("custom_properties") or {}).keys())
        valid_custom = {f"custom_properties.{key}" for key in custom_keys}
        invalid = {
            item for item in fields
            if not isinstance(item, str)
            or (item not in MESSAGEABLE_STANDARD_FIELDS and item not in valid_custom)
        }
        if invalid:
            raise ValueError(
                "message_fields contém campos não permitidos ou propriedades customizadas inexistentes: "
                + ", ".join(sorted(map(str, invalid)))
            )
        result["message_fields"] = list(dict.fromkeys(fields))

    result.setdefault("custom_properties", {})
    result.setdefault("message_fields", [])
    return result


async def refresh_engagement_profile(
    session: AsyncSession,
    *,
    tenant_id: str,
    student_id: str,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    """Recompute an engagement score and a bounded, explainable risk adjustment."""
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)
    settings = get_settings()
    cutoff_90d = current - timedelta(days=settings.engagement_history_days)
    cutoff_30d = current - timedelta(days=30)

    student_result = await session.execute(
        select(Student).where(Student.id == student_id, Student.tenant_id == tenant_id)
    )
    student = student_result.scalar_one_or_none()
    if not student:
        return None

    # This service is also called by the background worker, outside HTTP auth dependencies.
    await session.execute(text("SELECT set_config('app.tenant_id', :tenant_id, true)"), {"tenant_id": tenant_id})
    previous_risk_score = student.risk_score
    previous_risk_level = student.risk_level

    event_rows = (
        await session.execute(
            select(StudentEngagementEvent)
            .where(
                StudentEngagementEvent.tenant_id == tenant_id,
                StudentEngagementEvent.student_id == student_id,
                StudentEngagementEvent.occurred_at >= cutoff_90d,
            )
            .order_by(StudentEngagementEvent.occurred_at.asc())
        )
    ).scalars().all()

    # Score is a transparent decayed engagement index, not a newly trained ML probability.
    weighted_delta = 0.0
    replied_logs: set[str] = set()
    for event in event_rows:
        age_days = max(0.0, (current - event.occurred_at).total_seconds() / 86400.0)
        decay = 0.5 ** (age_days / 30.0)
        weighted_delta += _ENGAGEMENT_WEIGHTS.get(event.event_type, 0) * decay
        if event.event_type == "replied" and event.intervention_log_id:
            replied_logs.add(event.intervention_log_id)

    engagement_score = round(max(0.0, min(100.0, 50.0 + weighted_delta)), 1)
    no_response_logs = {
        event.intervention_log_id
        for event in event_rows
        if event.event_type == "no_response"
        and event.intervention_log_id
        and event.occurred_at >= cutoff_30d
        and event.intervention_log_id not in replied_logs
    }
    adjustment = round(min(15.0, len(no_response_logs) * 5.0), 1)

    if student.model_risk_score is None and student.risk_score is not None:
        # One-time baseline for records created before this feature.
        student.model_risk_score = float(student.risk_score)
    baseline = student.model_risk_score
    student.engagement_score = engagement_score
    student.engagement_score_updated_at = current
    student.dynamic_risk_adjustment = adjustment
    if baseline is not None:
        student.risk_score = round(max(0.0, min(100.0, float(baseline) + adjustment)), 1)
        student.risk_level = (
            "critico" if student.risk_score >= 70
            else "medio" if student.risk_score >= 40
            else "baixo"
        )
        # Persist only a real change in the stored risk score/classification.
        # Replayed engagement events and periodic sweeps with no score change do not
        # create duplicate historical assessments.
        if student.risk_score != previous_risk_score or student.risk_level != previous_risk_level:
            snapshot = student.shap_top_factors or {}
            model_version = snapshot.get("model_version")
            model_scope = snapshot.get("model_scope") or "base"
            session.add(RiskAssessment(
                tenant_id=tenant_id,
                student_id=student.id,
                batch_id=student.batch_id,
                scoring_run_id=str(__import__("uuid").uuid4()),
                evaluated_at=current,
                score=float(student.risk_score),
                risk_level=student.risk_level,
                model_version=str(model_version) if model_version is not None else None,
                model_scope=model_scope,
                model_score=float(student.model_risk_score) if student.model_risk_score is not None else None,
                dynamic_adjustment=adjustment,
                features_snapshot=build_features_from_student(student),
                explanation={
                    "available": bool(snapshot.get("top_3")),
                    "top_factors": snapshot.get("top_3") or None,
                    "summary": snapshot.get("summary"),
                    "note": "Fatores da avaliação base; o ajuste dinâmico foi atualizado por eventos de engajamento.",
                },
                context={"source": "engagement_refresh", "events_considered": len(event_rows), "no_response_events_30d": len(no_response_logs)},
            ))
    await session.flush()
    return {
        "student_id": student.id,
        "engagement_score": engagement_score,
        "model_risk_score": student.model_risk_score,
        "dynamic_risk_adjustment": adjustment,
        "risk_score": student.risk_score,
        "risk_level": student.risk_level,
        "events_considered": len(event_rows),
        "no_response_events_30d": len(no_response_logs),
        "updated_at": current.isoformat(),
    }


async def record_engagement_event(
    session: AsyncSession,
    *,
    tenant_id: str,
    student_id: str,
    event_key: str,
    event_type: str,
    channel: str | None,
    source: str,
    provider: str | None = None,
    intervention_log_id: str | None = None,
    occurred_at: datetime | None = None,
    event_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist one tenant-scoped interaction, deduplicate, and refresh student metrics."""
    if event_type not in _ALLOWED_EVENT_TYPES:
        raise ValueError(f"Tipo de evento de engajamento inválido: {event_type}")
    if not event_key or len(event_key) > 200:
        raise ValueError("event_key precisa ter entre 1 e 200 caracteres.")
    exists = await session.execute(
        select(StudentEngagementEvent.id).where(
            StudentEngagementEvent.tenant_id == tenant_id,
            StudentEngagementEvent.event_key == event_key,
        )
    )
    if exists.scalar_one_or_none():
        return {
            "created": False,
            "duplicate": True,
            "profile": await refresh_engagement_profile(
                session, tenant_id=tenant_id, student_id=student_id
            ),
        }

    event = StudentEngagementEvent(
        tenant_id=tenant_id,
        student_id=student_id,
        event_key=event_key,
        event_type=event_type,
        channel=channel,
        source=source[:40],
        provider=provider[:40] if provider else None,
        intervention_log_id=intervention_log_id,
        occurred_at=occurred_at or datetime.now(timezone.utc),
        event_metadata=event_metadata,
    )
    session.add(event)
    await session.flush()
    profile = await refresh_engagement_profile(
        session, tenant_id=tenant_id, student_id=student_id
    )
    await session.commit()
    return {"created": True, "duplicate": False, "event_id": event.id, "profile": profile}


async def is_sms_suppressed_by_recent_engagement(
    session: AsyncSession,
    *,
    tenant_id: str,
    student_id: str,
    now: datetime | None = None,
) -> bool:
    """Pause redundant SMS contacts after a recent click or reply."""
    settings = get_settings()
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    cutoff = current.astimezone(timezone.utc) - timedelta(
        hours=settings.engagement_channel_suppression_hours
    )
    result = await session.execute(
        select(StudentEngagementEvent.id)
        .where(
            StudentEngagementEvent.tenant_id == tenant_id,
            StudentEngagementEvent.student_id == student_id,
            StudentEngagementEvent.event_type.in_(["clicked", "replied"]),
            StudentEngagementEvent.occurred_at >= cutoff,
        )
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def recommend_send_time(
    session: AsyncSession,
    *,
    tenant_id: str,
    student_id: str,
    channels: list[str],
    now: datetime | None = None,
    timezone_name: str | None = None,
) -> dict[str, Any]:
    """Estimate a preferred send channel/hour from prior send-time to engagement pairs."""
    settings = get_settings()
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)
    try:
        local_zone = ZoneInfo(timezone_name or settings.engagement_timezone)
    except ZoneInfoNotFoundError:
        local_zone = ZoneInfo("America/Sao_Paulo")

    horizon = current - timedelta(days=settings.engagement_history_days)
    query = (
        select(InterventionLog)
        .where(
            InterventionLog.tenant_id == tenant_id,
            InterventionLog.student_id == student_id,
            InterventionLog.channel.in_(channels),
            InterventionLog.status == "sent",
            InterventionLog.created_at >= horizon,
        )
        .order_by(InterventionLog.created_at.desc())
        .limit(200)
    )
    logs = list((await session.execute(query)).scalars().all())
    log_ids = [log.id for log in logs]
    engaged_by_log: set[str] = set()
    if log_ids:
        event_rows = (
            await session.execute(
                select(StudentEngagementEvent.intervention_log_id).where(
                    StudentEngagementEvent.tenant_id == tenant_id,
                    StudentEngagementEvent.intervention_log_id.in_(log_ids),
                    StudentEngagementEvent.event_type.in_(sorted(_POSITIVE_EVENTS)),
                )
            )
        ).all()
        engaged_by_log = {row[0] for row in event_rows if row[0]}

    # Backwards compatibility for events received before the engagement-event table existed.
    stats: dict[tuple[str, int], list[int]] = {}
    channel_attempts: dict[str, int] = {}
    for log in logs:
        if not log.channel:
            continue
        local_hour = log.created_at.astimezone(local_zone).hour
        bucket = stats.setdefault((log.channel, local_hour), [0, 0])
        bucket[0] += 1
        positive = (
            log.id in engaged_by_log
            or log.outcome == "responded"
            or log.delivery_status in {"read", "opened", "clicked"}
        )
        bucket[1] += int(positive)
        channel_attempts[log.channel] = channel_attempts.get(log.channel, 0) + 1

    best: tuple[float, int, str, int, int] | None = None
    for (channel, hour), (attempts, engaged) in stats.items():
        if attempts < 3 or not 8 <= hour <= 20:
            continue
        # Laplace smoothing prevents a tiny sample from showing a perfect rate.
        rate = (engaged + 1.0) / (attempts + 2.0)
        candidate = (rate, attempts, channel, hour, engaged)
        if best is None or candidate[:2] > best[:2]:
            best = candidate

    if best:
        _rate, attempts, channel, hour, engaged = best
        confidence = "high" if attempts >= 10 else "medium"
        reason = "best_historical_send_hour"
        rate_pct = round(engaged / attempts * 100, 1)
        sample_size = attempts
    else:
        channel = channels[0] if channels else "email"
        hour = 10
        confidence = "fallback"
        reason = "insufficient_history_default_10am"
        rate_pct = None
        sample_size = channel_attempts.get(channel, 0)

    local_now = current.astimezone(local_zone)
    target = local_now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if target <= local_now + timedelta(minutes=15):
        target += timedelta(days=1)
    return {
        "student_id": student_id,
        "channel": channel,
        "preferred_hour_local": hour,
        "timezone": local_zone.key,
        "next_send_at": target.astimezone(timezone.utc).isoformat(),
        "confidence": confidence,
        "reason": reason,
        "historical_attempts_at_hour": sample_size,
        "engagement_rate_pct_at_hour": rate_pct,
        "history_days": settings.engagement_history_days,
    }


async def sweep_unanswered_reads(
    session: AsyncSession,
    *,
    now: datetime | None = None,
    response_window_hours: int | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Identify messages read but unanswered after the configured observation window."""
    settings = get_settings()
    window_hours = (
        settings.engagement_response_window_hours
        if response_window_hours is None
        else response_window_hours
    )
    if not 24 <= window_hours <= 168:
        raise ValueError("response_window_hours precisa estar entre 24 e 168 horas.")
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)
    threshold = current - timedelta(hours=window_hours)
    query = select(InterventionLog).where(
        InterventionLog.status == "sent",
        InterventionLog.delivery_status.in_(["read", "opened"]),
        InterventionLog.delivery_updated_at.is_not(None),
        InterventionLog.delivery_updated_at <= threshold,
        InterventionLog.outcome.is_(None),
        InterventionLog.student_id.is_not(None),
    )
    logs = list((await session.execute(query)).scalars().all())
    if not logs:
        return {
            "dry_run": dry_run, "response_window_hours": window_hours,
            "cutoff_utc": threshold.isoformat(), "candidates": 0,
            "events_created": 0, "students_updated": 0,
        }

    ids = [log.id for log in logs]
    existing_rows = await session.execute(
        select(StudentEngagementEvent.intervention_log_id, StudentEngagementEvent.event_type).where(
            StudentEngagementEvent.tenant_id.in_({log.tenant_id for log in logs}),
            StudentEngagementEvent.intervention_log_id.in_(ids),
            StudentEngagementEvent.event_type.in_(["no_response", "replied"]),
        )
    )
    existing_by_log: dict[str, set[str]] = {}
    for log_id, event_type in existing_rows.all():
        if log_id:
            existing_by_log.setdefault(log_id, set()).add(event_type)

    candidates = [
        log for log in logs
        if "no_response" not in existing_by_log.get(log.id, set())
        and "replied" not in existing_by_log.get(log.id, set())
    ]
    if dry_run:
        return {
            "dry_run": True, "response_window_hours": window_hours,
            "cutoff_utc": threshold.isoformat(), "candidates": len(candidates),
            "events_created": 0, "students_updated": 0,
        }

    students: set[tuple[str, str]] = set()
    for log in candidates:
        session.add(
            StudentEngagementEvent(
                tenant_id=log.tenant_id,
                student_id=log.student_id,
                intervention_log_id=log.id,
                event_key=f"auto-no-response:{log.id}",
                event_type="no_response",
                channel=log.channel,
                source="scheduled_sweep",
                provider=log.provider,
                occurred_at=current,
                event_metadata={"trigger": "read_without_response", "window_hours": window_hours},
            )
        )
        students.add((log.tenant_id, log.student_id))
    await session.flush()
    profiles = []
    for tenant_id, student_id in students:
        profile = await refresh_engagement_profile(
            session, tenant_id=tenant_id, student_id=student_id, now=current
        )
        if profile:
            profiles.append(profile)
    await session.commit()
    return {
        "dry_run": False, "response_window_hours": window_hours,
        "cutoff_utc": threshold.isoformat(), "candidates": len(candidates),
        "events_created": len(candidates), "students_updated": len(profiles),
        "profiles": profiles[:100],
    }
