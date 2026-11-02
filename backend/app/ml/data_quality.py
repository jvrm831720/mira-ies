"""Data-quality contract for predictive scoring.

Missing, invalid or out-of-range source values are never imputed as favorable
conditions. The current model was trained on complete synthetic rows, so scoring
is blocked until every raw input used to derive its 17 features is available.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any

FEATURE_SCHEMA_VERSION = "student-risk-features-v2"

# All seven source fields are required because every one contributes directly or
# indirectly to at least one model feature or business rule.
REQUIRED_SOURCE_FIELDS: dict[str, dict[str, Any]] = {
    "dias_atraso_boleto": {"label": "Dias de atraso financeiro", "type": "integer", "min": 0, "max": 3650},
    "recorrencia_atrasos": {"label": "Recorrência de atrasos", "type": "integer", "min": 0, "max": 100},
    "dias_sem_login": {"label": "Dias sem acesso ao AVA/LMS", "type": "integer", "min": 0, "max": 3650},
    "presenca_percentual": {"label": "Presença (%)", "type": "number", "min": 0, "max": 100},
    "nota_media": {"label": "Nota média", "type": "number", "min": 0, "max": 10},
    "reprovacoes": {"label": "Reprovações", "type": "integer", "min": 0, "max": 100},
    "semestre": {"label": "Semestre atual", "type": "integer", "min": 1, "max": 30},
}


class InsufficientDataError(ValueError):
    """Raised when a student cannot be scored from trustworthy source data."""

    def __init__(self, quality: dict[str, Any]):
        self.quality = quality
        labels = ", ".join(quality["missing_fields"] + quality["invalid_fields"])
        super().__init__(
            "Avaliação indeterminada: dados preditivos ausentes ou inválidos"
            + (f" ({labels})." if labels else ".")
        )


@dataclass(frozen=True)
class FieldIssue:
    field: str
    label: str
    reason: str


def _read(source: Any, field: str) -> Any:
    if isinstance(source, dict):
        return source.get(field)
    return getattr(source, field, None)


def assess_student_data_quality(source: Any) -> dict[str, Any]:
    missing: list[str] = []
    invalid: list[str] = []
    issues: list[dict[str, str]] = []
    observed = 0

    for field, spec in REQUIRED_SOURCE_FIELDS.items():
        value = _read(source, field)
        reason = None
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(field)
            reason = "missing"
        elif isinstance(value, bool):
            invalid.append(field)
            reason = "boolean_not_numeric"
        else:
            try:
                number = float(value)
                if not math.isfinite(number):
                    raise ValueError
                if spec["type"] == "integer" and not number.is_integer():
                    reason = "must_be_integer"
                elif number < spec["min"] or number > spec["max"]:
                    reason = "out_of_range"
            except (TypeError, ValueError, OverflowError):
                reason = "invalid_number"
            if reason:
                invalid.append(field)
            else:
                observed += 1

        if reason:
            issues.append({
                "field": field,
                "label": spec["label"],
                "reason": reason,
            })

    total = len(REQUIRED_SOURCE_FIELDS)
    complete = not missing and not invalid
    return {
        "status": "ready" if complete else "indeterminate",
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "required_fields": list(REQUIRED_SOURCE_FIELDS),
        "observed_fields": observed,
        "total_required_fields": total,
        "coverage_pct": round(observed / total * 100, 1),
        "missing_fields": missing,
        "invalid_fields": invalid,
        "issues": issues,
        "can_score": complete,
        "message": (
            "Dados completos para o contrato atual de features."
            if complete
            else "Score bloqueado: complete ou corrija os dados preditivos indicados."
        ),
    }


def require_scoreable_student(source: Any) -> dict[str, Any]:
    quality = assess_student_data_quality(source)
    if not quality["can_score"]:
        raise InsufficientDataError(quality)
    return quality
