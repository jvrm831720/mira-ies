"""Educational permanence outcomes and operational retention analytics.

Academic outcomes are reported only from confirmed, tenant-scoped SIS/import records.
Intervention associations are observational; this module never interprets them as causal effects.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthContext, get_current_tenant
from app.db.session import get_db
from app.ml.targets import EXCLUDED_OUTCOMES, normalize_utc_timestamp
from app.models.educational_outcome import AcademicOutcome
from app.models.intervention import InterventionLog
from app.models.retention_campaign import RetentionCampaign
from app.models.student import Student
from app.models.tenant import TrainingEvent

router = APIRouter()

_STAYED = frozenset({"rematriculado", "ativo", "concluiu", "formou"})
_EVASION = frozenset({"evadiu", "trancou"})
_DECISIVE = _STAYED | _EVASION
_DELIVERED = frozenset({"delivered", "read", "clicked", "replied"})
_ENGAGED = frozenset({"read", "clicked", "replied"})
_FAILED = frozenset({"failed", "rejected", "bounced", "invalid"})
_LOOKBACK_DAYS = 90
_MIN_GROUP_SIZE = 30
_MIN_STRATUM_SIZE = 10
_MIN_COMMON_SUPPORT = 0.8


def _identity(student_id: str | None, matricula: str | None) -> str:
    return f"matricula:{matricula}" if matricula else f"student:{student_id or 'unknown'}"


def _student_key(log: InterventionLog, student_by_id: dict[str, dict[str, Any]], student_by_matricula: dict[str, dict[str, Any]]) -> str:
    person = student_by_id.get(log.student_id or "") or student_by_matricula.get(log.matricula)
    return _identity((person or {}).get("id") or log.student_id, log.matricula)


def _risk_band(value: str | None) -> str | None:
    value = (value or "").strip().lower()
    return value if value in {"critico", "medio", "baixo"} else None


def _metric_counts(rows: list[dict[str, Any]]) -> dict[str, Any]:
    permanence = sum(row["outcome"] in _STAYED for row in rows)
    evasion = sum(row["outcome"] in _EVASION for row in rows)
    rematriculated = sum(row["outcome"] == "rematriculado" for row in rows)
    active = sum(row["outcome"] == "ativo" for row in rows)
    concluded = sum(row["outcome"] in {"concluiu", "formou"} for row in rows)
    transferred = sum(row["outcome"] in EXCLUDED_OUTCOMES for row in rows)
    denominator = permanence + evasion
    with_period = sum(bool(row["academic_period"]) for row in rows)
    with_source = sum(bool(row["outcome_source"]) for row in rows)
    return {
        "confirmed_outcomes": len(rows),
        "unique_students": len({row["identity"] for row in rows}),
        "rematriculados": rematriculated,
        "active_confirmed": active,
        "concluded": concluded,
        "permanence_outcomes": permanence,
        "evasion_outcomes": evasion,
        "transfers_excluded": transferred,
        "permanence_rate_pct": round(permanence / denominator * 100, 1) if denominator else None,
        "evasion_rate_pct": round(evasion / denominator * 100, 1) if denominator else None,
        "rematricula_share_pct": round(rematriculated / denominator * 100, 1) if denominator else None,
        "outcomes_with_academic_period": with_period,
        "academic_period_coverage_pct": round(with_period / len(rows) * 100, 1) if rows else None,
        "outcomes_with_source": with_source,
        "source_coverage_pct": round(with_source / len(rows) * 100, 1) if rows else None,
    }


def _group_rows(rows: list[dict[str, Any]], key: str, *, include_missing: bool = False) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        value = row.get(key)
        if value is None or value == "":
            if not include_missing:
                continue
            value = "_not_reported"
        buckets[str(value)].append(row)
    result = []
    for value, members in buckets.items():
        label = "Período letivo não informado" if value == "_not_reported" else value
        result.append({"key": value, "label": label, **_metric_counts(members)})
    return sorted(result, key=lambda item: (-item["confirmed_outcomes"], item["label"]))


def _event_log_window(logs: list[InterventionLog], observed_at: datetime) -> list[InterventionLog]:
    observed = normalize_utc_timestamp(observed_at)
    start = observed - timedelta(days=_LOOKBACK_DAYS)
    return [
        log for log in logs
        if log.status == "sent"
        and start <= normalize_utc_timestamp(log.created_at) <= observed
    ]


def _comparison(rows: list[dict[str, Any]], *, campaign_id: str | None, channel: str | None) -> dict[str, Any]:
    exposed: list[dict[str, Any]] = []
    controls: list[dict[str, Any]] = []
    mixed = 0
    missing_risk = 0

    for row in rows:
        if row["outcome"] not in _DECISIVE:
            continue
        sent = row["sent_interventions"]
        if campaign_id or channel:
            matching = [
                log for log in sent
                if (not campaign_id or log.campaign_id == campaign_id)
                and (not channel or log.channel == channel)
            ]
            if matching and len(matching) == len(sent):
                group = exposed
            elif not sent:
                group = controls
            else:
                mixed += 1
                continue
        elif sent:
            group = exposed
        else:
            group = controls

        band = _risk_band(row["baseline_risk_level"])
        if band is None:
            missing_risk += 1
            continue
        group.append({"risk_band": band, "retained": row["outcome"] in _STAYED})

    result: dict[str, Any] = {
        "status": "insufficient_data",
        "method": "Comparação observacional estratificada pela faixa de risco basal; apenas intervenções com status enviado e desfechos acadêmicos confirmados.",
        "causal_claim": False,
        "minimum_group_size": _MIN_GROUP_SIZE,
        "minimum_per_stratum": _MIN_STRATUM_SIZE,
        "exposed_n": len(exposed),
        "no_intervention_n": len(controls),
        "mixed_exposure_excluded": mixed,
        "missing_baseline_risk_excluded": missing_risk,
        "permanence_rate_exposed_pct": None,
        "permanence_rate_no_intervention_standardized_pct": None,
        "difference_percentage_points": None,
        "reason": "A comparação só é exibida quando há grupos e faixas de risco basal com suporte comum suficiente.",
    }
    if len(exposed) < _MIN_GROUP_SIZE or len(controls) < _MIN_GROUP_SIZE:
        result["reason"] = f"Dados insuficientes: são necessários pelo menos {_MIN_GROUP_SIZE} outcomes elegíveis em cada grupo."
        return result

    exposed_by_band: dict[str, list[dict[str, Any]]] = defaultdict(list)
    controls_by_band: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in exposed:
        exposed_by_band[row["risk_band"]].append(row)
    for row in controls:
        controls_by_band[row["risk_band"]].append(row)

    common_bands = [
        band for band in ("critico", "medio", "baixo")
        if len(exposed_by_band[band]) >= _MIN_STRATUM_SIZE
        and len(controls_by_band[band]) >= _MIN_STRATUM_SIZE
    ]
    covered_exposed = sum(len(exposed_by_band[band]) for band in common_bands)
    if not common_bands or covered_exposed / len(exposed) < _MIN_COMMON_SUPPORT:
        result["reason"] = "Sem suporte comum suficiente entre os grupos nas faixas de risco basal; a comparação foi suprimida."
        return result

    exposed_weighted = 0.0
    control_standardized = 0.0
    for band in common_bands:
        weight = len(exposed_by_band[band]) / covered_exposed
        exposed_rate = sum(item["retained"] for item in exposed_by_band[band]) / len(exposed_by_band[band])
        control_rate = sum(item["retained"] for item in controls_by_band[band]) / len(controls_by_band[band])
        exposed_weighted += exposed_rate * weight
        control_standardized += control_rate * weight

    exposed_pct = round(exposed_weighted * 100, 1)
    control_pct = round(control_standardized * 100, 1)
    result.update({
        "status": "available_descriptive",
        "common_risk_bands": common_bands,
        "exposed_coverage_common_support_pct": round(covered_exposed / len(exposed) * 100, 1),
        "permanence_rate_exposed_pct": exposed_pct,
        "permanence_rate_no_intervention_standardized_pct": control_pct,
        "difference_percentage_points": round(exposed_pct - control_pct, 1),
        "reason": "Diferença descritiva padronizada por faixa de risco basal; não demonstra efeito causal da intervenção.",
    })
    return result


def _operational_metrics(logs: list[InterventionLog], student_by_id: dict[str, dict[str, Any]], student_by_matricula: dict[str, dict[str, Any]]) -> dict[str, Any]:
    sent = [log for log in logs if log.status == "sent"]
    delivered = [log for log in logs if log.delivery_status in _DELIVERED]
    engaged = [log for log in logs if log.delivery_status in _ENGAGED]
    failed = [log for log in logs if log.status == "failed" or log.delivery_status in _FAILED]
    return {
        "records": len(logs),
        "messages_sent": len(sent),
        "unique_students_contacted": len({_student_key(log, student_by_id, student_by_matricula) for log in sent}),
        "delivered_messages": len(delivered),
        "engaged_messages": len(engaged),
        "failed_messages": len(failed),
        "delivery_rate_pct": round(len(delivered) / len(sent) * 100, 1) if sent else None,
        "engagement_rate_pct": round(len(engaged) / len(sent) * 100, 1) if sent else None,
    }


def _operational_breakdown(logs: list[InterventionLog], key_fn) -> list[dict[str, Any]]:
    grouped: dict[str, list[InterventionLog]] = defaultdict(list)
    labels: dict[str, str] = {}
    for log in logs:
        key, label = key_fn(log)
        if key is None:
            continue
        grouped[str(key)].append(log)
        labels[str(key)] = str(label or key)
    result = []
    for key, members in grouped.items():
        sent = [log for log in members if log.status == "sent"]
        result.append({
            "key": key,
            "label": labels[key],
            "records": len(members),
            "messages_sent": len(sent),
            "unique_students_contacted": len({log.matricula for log in sent}),
            "delivered_messages": sum(log.delivery_status in _DELIVERED for log in members),
        })
    return sorted(result, key=lambda row: (-row["messages_sent"], row["label"]))


@router.get("/outcomes/analytics")
async def educational_outcomes_analytics(
    days: int = Query(365, ge=1, le=1095),
    academic_period: str | None = Query(default=None, min_length=1, max_length=40),
    course: str | None = Query(default=None, min_length=1, max_length=150),
    campaign_id: str | None = Query(default=None, min_length=1, max_length=120),
    channel: str | None = Query(default=None, pattern=r"^(whatsapp|email|sms)$"),
    auth: AuthContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Aggregate confirmed academic outcomes separately from contact operations."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)
    outcome_result = await db.execute(
        select(AcademicOutcome)
        .where(
            AcademicOutcome.tenant_id == auth.tenant_id,
            AcademicOutcome.observed_at >= cutoff,
            AcademicOutcome.observed_at <= now,
        )
        .order_by(AcademicOutcome.observed_at.desc())
    )
    academic_outcomes = list(outcome_result.scalars().all())

    student_ids = {outcome.student_id for outcome in academic_outcomes if outcome.student_id}
    matriculas = {outcome.matricula for outcome in academic_outcomes if outcome.matricula}
    student_predicates = []
    if student_ids:
        student_predicates.append(Student.id.in_(student_ids))
    if matriculas:
        student_predicates.append(Student.matricula.in_(matriculas))
    students: list[dict[str, Any]] = []
    if student_predicates:
        student_rows = (await db.execute(
            select(Student.id, Student.matricula, Student.nome, Student.curso, Student.updated_at)
            .where(Student.tenant_id == auth.tenant_id, *student_predicates)
            .order_by(Student.updated_at.desc())
        )).all()
        students = [
            {"id": row.id, "matricula": row.matricula, "name": row.nome, "course": row.curso}
            for row in student_rows
        ]
    student_by_id = {student["id"]: student for student in students}
    student_by_matricula: dict[str, dict[str, Any]] = {}
    for student in students:
        student_by_matricula.setdefault(student["matricula"], student)

    # Baseline risk is the latest score at or before the academic observation. A score
    # after the outcome is never used to select comparison strata.
    score_result = await db.execute(
        select(TrainingEvent)
        .where(
            TrainingEvent.tenant_id == auth.tenant_id,
            TrainingEvent.matricula.in_(matriculas) if matriculas else TrainingEvent.id.is_(None),
            TrainingEvent.scored_at <= now,
        )
        .order_by(TrainingEvent.scored_at.desc())
    )
    scores_by_matricula: dict[str, list[TrainingEvent]] = defaultdict(list)
    for score in score_result.scalars().all():
        scores_by_matricula[score.matricula].append(score)

    earliest_outcome = min(
        (normalize_utc_timestamp(outcome.observed_at) for outcome in academic_outcomes),
        default=cutoff,
    )
    log_cutoff = min(cutoff, earliest_outcome - timedelta(days=_LOOKBACK_DAYS))
    log_result = await db.execute(
        select(InterventionLog)
        .where(
            InterventionLog.tenant_id == auth.tenant_id,
            InterventionLog.created_at >= log_cutoff,
            InterventionLog.created_at <= now,
        )
        .order_by(InterventionLog.created_at.desc())
    )
    all_logs = list(log_result.scalars().all())
    logs_by_identity: dict[str, list[InterventionLog]] = defaultdict(list)
    operational_logs: list[InterventionLog] = []
    for log in all_logs:
        logs_by_identity[_student_key(log, student_by_id, student_by_matricula)].append(log)
        if normalize_utc_timestamp(log.created_at) < cutoff:
            continue
        person = student_by_id.get(log.student_id or "") or student_by_matricula.get(log.matricula)
        log_course = (person or {}).get("course")
        if course and log_course != course:
            continue
        if channel and log.channel != channel:
            continue
        if campaign_id and log.campaign_id != campaign_id:
            continue
        operational_logs.append(log)

    campaign_rows = (await db.execute(
        select(RetentionCampaign.id, RetentionCampaign.name).where(RetentionCampaign.tenant_id == auth.tenant_id)
    )).all()
    campaign_names = {str(row.id): row.name for row in campaign_rows}

    raw_records: list[dict[str, Any]] = []
    for outcome in academic_outcomes:
        person = student_by_id.get(outcome.student_id or "") or student_by_matricula.get(outcome.matricula)
        resolved_student_id = (person or {}).get("id") or outcome.student_id
        identity = _identity(resolved_student_id, outcome.matricula)
        observed = normalize_utc_timestamp(outcome.observed_at)
        sent = _event_log_window(logs_by_identity.get(identity, []), observed)
        matching = [
            log for log in sent
            if (not campaign_id or log.campaign_id == campaign_id)
            and (not channel or log.channel == channel)
        ]
        course_value = outcome.course or (person or {}).get("course")
        period_value = (outcome.academic_period or "").strip() or None
        if course and course_value != course:
            continue
        if academic_period and period_value != academic_period:
            continue
        if (campaign_id or channel) and not matching:
            continue
        baseline = next(
            (score for score in scores_by_matricula.get(outcome.matricula, [])
             if normalize_utc_timestamp(score.scored_at) <= observed),
            None,
        )
        raw_records.append({
            "event_id": outcome.id,
            "identity": identity,
            "student_id": resolved_student_id,
            "matricula": outcome.matricula,
            "student_name": (person or {}).get("name"),
            "course": course_value,
            "outcome": (outcome.outcome or "").strip().lower(),
            "outcome_at": observed.isoformat(),
            "academic_period": period_value,
            "academic_period_reported": period_value is not None,
            "outcome_source": outcome.source,
            "source_record_id": outcome.source_record_id,
            "baseline_risk_level": baseline.risk_level if baseline else None,
            "sent_interventions": sent,
            "matching_interventions": matching if (campaign_id or channel) else sent,
        })

    # A student contributes at most one latest confirmed status per academic period
    # to rates. Without a reported period, deduplicate same-day imports only.
    deduplicated: dict[tuple[str, str], dict[str, Any]] = {}
    for row in raw_records:
        period_key = row["academic_period"] or f"_date:{row['outcome_at'][:10]}"
        key = (row["identity"], period_key)
        prior = deduplicated.get(key)
        if prior is None or row["outcome_at"] > prior["outcome_at"]:
            deduplicated[key] = row
    educational_rows = sorted(deduplicated.values(), key=lambda row: row["outcome_at"], reverse=True)

    campaign_outcomes: dict[str, dict[str, Any]] = {}
    channel_outcomes: dict[str, dict[str, Any]] = {}
    for row in educational_rows:
        seen_campaigns: set[str] = set()
        seen_channels: set[str] = set()
        for log in row["matching_interventions"]:
            if log.campaign_id:
                key = str(log.campaign_id)
                if key not in seen_campaigns:
                    seen_campaigns.add(key)
                    campaign_outcomes.setdefault(key, {"key": key, "label": campaign_names.get(key, key), "rows": []})["rows"].append(row)
            if log.channel:
                key = str(log.channel)
                if key not in seen_channels:
                    seen_channels.add(key)
                    channel_outcomes.setdefault(key, {"key": key, "label": key, "rows": []})["rows"].append(row)

    outcome_labels = {
        "rematriculado": "Rematriculado",
        "ativo": "Ativo confirmado",
        "evadiu": "Evasão confirmada",
        "trancou": "Trancamento",
        "concluiu": "Conclusão",
        "formou": "Formatura",
        "transferiu": "Transferência (fora do denominador de permanência/evasão)",
    }
    education_records = []
    for row in raw_records[:100]:
        interventions = row["matching_interventions"]
        education_records.append({
            "event_id": row["event_id"],
            "student_id": row["student_id"],
            "matricula": row["matricula"],
            "student_name": row["student_name"],
            "course": row["course"],
            "outcome": row["outcome"],
            "outcome_label": outcome_labels.get(row["outcome"], row["outcome"].replace("_", " ").title()),
            "outcome_at": row["outcome_at"],
            "academic_period": row["academic_period"],
            "academic_period_reported": row["academic_period_reported"],
            "outcome_source": row["outcome_source"],
            "intervention_count": len(interventions),
            "campaigns": sorted({campaign_names.get(str(log.campaign_id), str(log.campaign_id)) for log in interventions if log.campaign_id}),
            "channels": sorted({str(log.channel) for log in interventions if log.channel}),
        })

    month_groups: dict[str, list[InterventionLog]] = defaultdict(list)
    for log in operational_logs:
        month_groups[normalize_utc_timestamp(log.created_at).strftime("%Y-%m")].append(log)
    operational_period_rows = [
        {"key": month, "label": month, **_operational_metrics(members, student_by_id, student_by_matricula)}
        for month, members in sorted(month_groups.items(), reverse=True)
    ]

    def course_for_log(log: InterventionLog) -> str | None:
        person = student_by_id.get(log.student_id or "") or student_by_matricula.get(log.matricula)
        return (person or {}).get("course")

    operations = {
        "summary": _operational_metrics(operational_logs, student_by_id, student_by_matricula),
        "by_campaign": _operational_breakdown(
            operational_logs,
            lambda log: (str(log.campaign_id), campaign_names.get(str(log.campaign_id), str(log.campaign_id))) if log.campaign_id else (None, None),
        ),
        "by_channel": _operational_breakdown(operational_logs, lambda log: (log.channel or "_none", log.channel or "Sem canal")),
        "by_course": _operational_breakdown(operational_logs, lambda log: (course_for_log(log), course_for_log(log))),
        "by_calendar_month": operational_period_rows,
    }
    education = {
        "summary": _metric_counts(educational_rows),
        "by_academic_period": _group_rows(educational_rows, "academic_period", include_missing=True),
        "by_course": _group_rows(educational_rows, "course"),
        "by_campaign": [
            {"key": key, "label": bucket["label"], **_metric_counts(bucket["rows"])}
            for key, bucket in sorted(campaign_outcomes.items(), key=lambda item: (-len(item[1]["rows"]), item[1]["label"]))
        ],
        "by_channel": [
            {"key": key, "label": bucket["label"], **_metric_counts(bucket["rows"])}
            for key, bucket in sorted(channel_outcomes.items(), key=lambda item: (-len(item[1]["rows"]), item[1]["label"]))
        ],
        "source_events_total": len(raw_records),
        "records_total": len(raw_records),
        "records": education_records,
    }

    course_rows = (await db.execute(
        select(distinct(Student.curso)).where(Student.tenant_id == auth.tenant_id, Student.curso.is_not(None))
    )).scalars().all()
    course_options = {str(value) for value in course_rows if value}
    course_options.update(outcome.course for outcome in academic_outcomes if outcome.course)
    period_options = sorted({(outcome.academic_period or "").strip() for outcome in academic_outcomes if (outcome.academic_period or "").strip()})
    channel_options = sorted({str(log.channel) for log in all_logs if log.channel in {"whatsapp", "email", "sms"}})
    campaign_option_names = {str(row.id): row.name for row in campaign_rows}
    for log in all_logs:
        if log.campaign_id:
            campaign_option_names.setdefault(str(log.campaign_id), str(log.campaign_id))
    campaign_options = [{"id": key, "name": value} for key, value in sorted(campaign_option_names.items(), key=lambda item: item[1].lower())]

    return {
        "generated_at": now.isoformat(),
        "period_days": days,
        "filters_applied": {
            "academic_period": academic_period,
            "course": course,
            "campaign_id": campaign_id,
            "channel": channel,
        },
        "options": {
            "academic_periods": period_options,
            "courses": sorted(course_options),
            "campaigns": campaign_options,
            "channels": channel_options,
        },
        "educational": education,
        "operational": operations,
        "comparison": _comparison(raw_records, campaign_id=campaign_id, channel=channel),
        "methodology": {
            "outcome_source": "Desfechos acadêmicos confirmados importados em academic_outcomes, sem dependência de snapshot de score.",
            "permanence_definition": "Rematrícula, ativo, conclusão ou formatura confirmados; evasão e trancamento compõem o grupo de saída. Transferência fica fora das taxas.",
            "intervention_window_days": _LOOKBACK_DAYS,
            "causality": "Associação temporal não prova que uma intervenção causou permanência ou evasão.",
            "academic_period": "Somente o período letivo informado pela origem acadêmica é tratado como período acadêmico; registros sem esse campo permanecem sem período informado.",
            "operational_period": "A série operacional usa mês-calendário e não deve ser interpretada como período letivo.",
            "comparison": "A comparação só é apresentada com pelo menos 30 outcomes elegíveis por grupo, 10 por faixa de risco basal e 80% de suporte comum; caso contrário, os valores são suprimidos.",
        },
    }
