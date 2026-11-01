"""Avaliação pura dos grupos virtuais sobre resultados de sinais pré-carregados."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from app.signals.evaluate import SignalEvaluation, evaluate_student_signals
from app.student_groups.catalog import (
    GROUP_DEFINITIONS,
    GroupState,
    OPERATIONAL_SIGNAL_IDS,
)


@dataclass(frozen=True)
class GroupEvaluation:
    group_id: str
    state: GroupState
    evidence: dict[str, Any]
    evaluated_at: str
    limitations: list[str]


@dataclass(frozen=True)
class StudentGroupsEvaluation:
    student_id: str
    tenant_id: str
    evaluated_at: str
    groups: list[GroupEvaluation]


def _state_for_signal(signal: SignalEvaluation) -> GroupState:
    if signal.insufficient_data:
        return "INDETERMINATE"
    return "TRUE" if signal.active else "FALSE"


def _group_limitations(group_id: str) -> list[str]:
    definition = next(item for item in GROUP_DEFINITIONS if item.id == group_id)
    return list(definition.limitations)


def _single_group(group_id: str, signal: SignalEvaluation, evaluated_at: str) -> GroupEvaluation:
    return GroupEvaluation(
        group_id=group_id,
        state=_state_for_signal(signal),
        evidence={
            "signal_id": signal.signal_id,
            "signal_active": signal.active,
            "signal_insufficient_data": signal.insufficient_data,
            "signal_evidence": signal.evidence,
        },
        evaluated_at=evaluated_at,
        limitations=_group_limitations(group_id),
    )


def evaluate_multiple_active_signals(
    signals: Mapping[str, SignalEvaluation], evaluated_at: str
) -> GroupEvaluation:
    operational = [signals[signal_id] for signal_id in OPERATIONAL_SIGNAL_IDS]
    active_count = sum(signal.active and not signal.insufficient_data for signal in operational)
    indeterminate_count = sum(signal.insufficient_data for signal in operational)
    if active_count >= 2:
        state: GroupState = "TRUE"
    elif active_count + indeterminate_count >= 2:
        state = "INDETERMINATE"
    else:
        state = "FALSE"
    return GroupEvaluation(
        group_id="multiple_active_signals",
        state=state,
        evidence={
            "operational_signal_ids": list(OPERATIONAL_SIGNAL_IDS),
            "active_count": active_count,
            "indeterminate_count": indeterminate_count,
            "threshold": 2,
            "missing_score_excluded": True,
        },
        evaluated_at=evaluated_at,
        limitations=_group_limitations("multiple_active_signals"),
    )


def evaluate_student_groups(
    *,
    student_id: str,
    tenant_id: str,
    student: Mapping[str, Any],
    assessments: Sequence[Mapping[str, Any]] | None = None,
    history_unavailable: bool = False,
    evaluated_at: datetime | None = None,
) -> StudentGroupsEvaluation:
    timestamp = (evaluated_at or datetime.now(timezone.utc)).isoformat()
    signal_result = evaluate_student_signals(
        student_id=student_id,
        tenant_id=tenant_id,
        student=student,
        assessments=assessments,
        history_unavailable=history_unavailable,
        evaluated_at=evaluated_at,
    )
    by_id = {signal.signal_id: signal for signal in signal_result.signals}
    groups: list[GroupEvaluation] = []
    for definition in GROUP_DEFINITIONS:
        if definition.id == "multiple_active_signals":
            groups.append(evaluate_multiple_active_signals(by_id, timestamp))
        else:
            groups.append(_single_group(definition.id, by_id[definition.signal_ids[0]], timestamp))
    return StudentGroupsEvaluation(
        student_id=student_id,
        tenant_id=tenant_id,
        evaluated_at=timestamp,
        groups=groups,
    )


def serialize_group_evaluation(evaluation: GroupEvaluation) -> dict[str, Any]:
    return {
        "id": evaluation.group_id,
        "state": evaluation.state,
        "matched": evaluation.state == "TRUE",
        "evidence": evaluation.evidence,
        "evaluated_at": evaluation.evaluated_at,
        "limitations": evaluation.limitations,
    }
