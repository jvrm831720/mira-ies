"""Avaliação sob demanda dos seis sinais autorizados.

Funções puras sobre snapshots de aluno e histórico de risco.
NULL / ausente → insufficient_data (exceto missing_score, que é o meta-sinal).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from app.signals.catalog import (
    DAYS_WITHOUT_LOGIN_THRESHOLD,
    FINANCIAL_DELAY_DAYS_THRESHOLD,
    RISK_INCREASE_SCORE_DELTA,
    SIGNAL_CATALOG,
)

_VALID_LEVELS = frozenset({"baixo", "medio", "critico"})
_LEVEL_RANK = {"baixo": 1, "medio": 2, "critico": 3}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _finite_score(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if not isinstance(value, (int, float)):
        return None
    if not math.isfinite(float(value)):
        return None
    score = float(value)
    if score < 0 or score > 100:
        return None
    return score


def _complete_risk(level: Any, score: Any) -> bool:
    return level in _VALID_LEVELS and _finite_score(score) is not None


@dataclass
class SignalEvaluation:
    signal_id: str
    active: bool
    insufficient_data: bool
    evidence: dict[str, Any]
    evaluated_at: str
    signal_version: str
    limitations: list[str] = field(default_factory=list)


@dataclass
class EvaluationResult:
    student_id: str
    tenant_id: str
    evaluated_at: str
    signals: list[SignalEvaluation]

    def active_ids(self) -> list[str]:
        return [s.signal_id for s in self.signals if s.active]


def _base(
    signal_id: str,
    *,
    active: bool,
    insufficient_data: bool,
    evidence: dict[str, Any],
    evaluated_at: str,
) -> SignalEvaluation:
    defn = SIGNAL_CATALOG[signal_id]
    return SignalEvaluation(
        signal_id=signal_id,
        active=active,
        insufficient_data=insufficient_data,
        evidence=evidence,
        evaluated_at=evaluated_at,
        signal_version=str(defn["version"]),
        limitations=list(defn.get("limitations") or []),
    )


def evaluate_risk_critical(student: Mapping[str, Any], evaluated_at: str) -> SignalEvaluation:
    level = student.get("risk_level")
    score = student.get("risk_score")
    if not _complete_risk(level, score):
        return _base(
            "risk_critical",
            active=False,
            insufficient_data=True,
            evidence={"risk_level": level, "risk_score": score, "reason": "score_or_level_incomplete"},
            evaluated_at=evaluated_at,
        )
    active = level == "critico"
    return _base(
        "risk_critical",
        active=active,
        insufficient_data=False,
        evidence={
            "risk_level": level,
            "risk_score": float(score),
            "matched": active,
        },
        evaluated_at=evaluated_at,
    )


def evaluate_risk_medium(student: Mapping[str, Any], evaluated_at: str) -> SignalEvaluation:
    level = student.get("risk_level")
    score = student.get("risk_score")
    if not _complete_risk(level, score):
        return _base(
            "risk_medium",
            active=False,
            insufficient_data=True,
            evidence={"risk_level": level, "risk_score": score, "reason": "score_or_level_incomplete"},
            evaluated_at=evaluated_at,
        )
    active = level == "medio"
    return _base(
        "risk_medium",
        active=active,
        insufficient_data=False,
        evidence={
            "risk_level": level,
            "risk_score": float(score),
            "matched": active,
        },
        evaluated_at=evaluated_at,
    )


def evaluate_missing_score(student: Mapping[str, Any], evaluated_at: str) -> SignalEvaluation:
    """Meta-sinal: ativo quando NÃO há score utilizável."""
    level = student.get("risk_level")
    score = student.get("risk_score")
    complete = _complete_risk(level, score)
    return _base(
        "missing_score",
        active=not complete,
        insufficient_data=False,  # a própria ausência é o fato observado
        evidence={
            "risk_level": level,
            "risk_score": score,
            "has_usable_score": complete,
            "note": "Não indica baixo risco; indica cobertura insuficiente.",
        },
        evaluated_at=evaluated_at,
    )


def evaluate_financial_delay(student: Mapping[str, Any], evaluated_at: str) -> SignalEvaluation:
    raw = student.get("dias_atraso_boleto")
    if raw is None:
        return _base(
            "financial_delay",
            active=False,
            insufficient_data=True,
            evidence={"dias_atraso_boleto": None, "reason": "field_null"},
            evaluated_at=evaluated_at,
        )
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return _base(
            "financial_delay",
            active=False,
            insufficient_data=True,
            evidence={"dias_atraso_boleto": raw, "reason": "invalid_type"},
            evaluated_at=evaluated_at,
        )
    if not math.isfinite(float(raw)) or float(raw) < 0:
        return _base(
            "financial_delay",
            active=False,
            insufficient_data=True,
            evidence={"dias_atraso_boleto": raw, "reason": "invalid_value"},
            evaluated_at=evaluated_at,
        )
    days = int(raw)
    active = days >= FINANCIAL_DELAY_DAYS_THRESHOLD
    return _base(
        "financial_delay",
        active=active,
        insufficient_data=False,
        evidence={
            "dias_atraso_boleto": days,
            "threshold": FINANCIAL_DELAY_DAYS_THRESHOLD,
            "matched": active,
        },
        evaluated_at=evaluated_at,
    )


def evaluate_days_without_login(student: Mapping[str, Any], evaluated_at: str) -> SignalEvaluation:
    raw = student.get("dias_sem_login")
    if raw is None:
        return _base(
            "days_without_login_elevated",
            active=False,
            insufficient_data=True,
            evidence={"dias_sem_login": None, "reason": "field_null"},
            evaluated_at=evaluated_at,
        )
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return _base(
            "days_without_login_elevated",
            active=False,
            insufficient_data=True,
            evidence={"dias_sem_login": raw, "reason": "invalid_type"},
            evaluated_at=evaluated_at,
        )
    if not math.isfinite(float(raw)) or float(raw) < 0:
        return _base(
            "days_without_login_elevated",
            active=False,
            insufficient_data=True,
            evidence={"dias_sem_login": raw, "reason": "invalid_value"},
            evaluated_at=evaluated_at,
        )
    days = int(raw)
    active = days >= DAYS_WITHOUT_LOGIN_THRESHOLD
    return _base(
        "days_without_login_elevated",
        active=active,
        insufficient_data=False,
        evidence={
            "dias_sem_login": days,
            "threshold": DAYS_WITHOUT_LOGIN_THRESHOLD,
            "matched": active,
        },
        evaluated_at=evaluated_at,
    )


def evaluate_risk_increase(
    assessments: Sequence[Mapping[str, Any]],
    evaluated_at: str,
    *,
    history_unavailable: bool = False,
) -> SignalEvaluation:
    if history_unavailable:
        return _base(
            "risk_increase",
            active=False,
            insufficient_data=True,
            evidence={"reason": "history_schema_or_query_unavailable"},
            evaluated_at=evaluated_at,
        )
    if len(assessments) < 2:
        return _base(
            "risk_increase",
            active=False,
            insufficient_data=True,
            evidence={
                "assessments_count": len(assessments),
                "reason": "need_at_least_two_assessments",
            },
            evaluated_at=evaluated_at,
        )

    # Esperado: ordenado do mais recente para o mais antigo
    current, previous = assessments[0], assessments[1]
    cur_mv = current.get("model_version")
    prev_mv = previous.get("model_version")
    cur_sem = current.get("score_semantics_version")
    prev_sem = previous.get("score_semantics_version")

    if cur_mv != prev_mv or cur_sem != prev_sem:
        return _base(
            "risk_increase",
            active=False,
            insufficient_data=True,
            evidence={
                "reason": "incomparable_model_or_semantics",
                "current_model_version": cur_mv,
                "previous_model_version": prev_mv,
                "current_score_semantics_version": cur_sem,
                "previous_score_semantics_version": prev_sem,
                "note": "Mudança de modelo não é interpretada como aumento de risco.",
            },
            evaluated_at=evaluated_at,
        )

    cur_score = _finite_score(current.get("score"))
    prev_score = _finite_score(previous.get("score"))
    cur_level = current.get("risk_level")
    prev_level = previous.get("risk_level")
    if cur_score is None or prev_score is None or cur_level not in _VALID_LEVELS or prev_level not in _VALID_LEVELS:
        return _base(
            "risk_increase",
            active=False,
            insufficient_data=True,
            evidence={
                "reason": "incomplete_assessment_fields",
                "current_score": current.get("score"),
                "previous_score": previous.get("score"),
                "current_level": cur_level,
                "previous_level": prev_level,
            },
            evaluated_at=evaluated_at,
        )

    delta = cur_score - prev_score
    level_up = _LEVEL_RANK[cur_level] > _LEVEL_RANK[prev_level]
    score_up = delta >= RISK_INCREASE_SCORE_DELTA
    active = bool(level_up or score_up)
    return _base(
        "risk_increase",
        active=active,
        insufficient_data=False,
        evidence={
            "current_score": cur_score,
            "previous_score": prev_score,
            "delta": round(delta, 4),
            "threshold_delta": RISK_INCREASE_SCORE_DELTA,
            "current_level": cur_level,
            "previous_level": prev_level,
            "level_upgraded": level_up,
            "score_increased": score_up,
            "model_version": cur_mv,
            "score_semantics_version": cur_sem,
            "matched": active,
        },
        evaluated_at=evaluated_at,
    )


def evaluate_student_signals(
    *,
    student_id: str,
    tenant_id: str,
    student: Mapping[str, Any],
    assessments: Sequence[Mapping[str, Any]] | None = None,
    history_unavailable: bool = False,
    evaluated_at: datetime | None = None,
) -> EvaluationResult:
    ts = (evaluated_at or _now()).isoformat()
    hist = list(assessments or [])
    signals = [
        evaluate_risk_critical(student, ts),
        evaluate_risk_medium(student, ts),
        evaluate_missing_score(student, ts),
        evaluate_financial_delay(student, ts),
        evaluate_days_without_login(student, ts),
        evaluate_risk_increase(hist, ts, history_unavailable=history_unavailable),
    ]
    return EvaluationResult(
        student_id=student_id,
        tenant_id=tenant_id,
        evaluated_at=ts,
        signals=signals,
    )


def serialize_evaluation(ev: SignalEvaluation) -> dict[str, Any]:
    return {
        "signal_id": ev.signal_id,
        "active": ev.active,
        "insufficient_data": ev.insufficient_data,
        "evidence": ev.evidence,
        "evaluated_at": ev.evaluated_at,
        "signal_version": ev.signal_version,
        "limitations": ev.limitations,
    }
