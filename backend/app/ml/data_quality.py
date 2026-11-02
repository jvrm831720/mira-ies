"""Data-quality contract for predictive scoring.

Missing, invalid or out-of-range source values are never imputed as favorable
conditions. The current model was trained on complete synthetic rows, so scoring
is blocked until every raw input used to derive its 17 features is available.
"""
from __future__ import annotations

import math
from typing import Any

FEATURE_SCHEMA_VERSION = "student-risk-features-v2"
from datetime import datetime, timezone

# Limites conservadoras para idade da observação, quando a origem informar
# explicitamente quando o dado foi medido. Importar hoje não prova que o dado
# foi observado hoje.
FIELD_MAX_AGE_DAYS: dict[str, int] = {
    "dias_atraso_boleto": 30,
    "recorrencia_atrasos": 30,
    "dias_sem_login": 7,
    "presenca_percentual": 30,
    "nota_media": 90,
    "reprovacoes": 90,
    "semestre": 180,
}


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def assess_field_freshness(source: Any, *, now: datetime | None = None) -> dict[str, Any]:
    """Avalia idade da observação sem confundir data de importação com data de medição."""
    raw_data = _read(source, "raw_data") or {}
    provenance = raw_data.get("_mira_provenance", {}) if isinstance(raw_data, dict) else {}
    now_utc = now or datetime.now(timezone.utc)
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    else:
        now_utc = now_utc.astimezone(timezone.utc)
    fields: dict[str, Any] = {}
    counts = {"fresh": 0, "aging": 0, "stale": 0, "unknown": 0}
    for field, max_age in FIELD_MAX_AGE_DAYS.items():
        metadata = provenance.get(field, {}) if isinstance(provenance, dict) else {}
        observed_at = _parse_timestamp(metadata.get("observed_at")) if isinstance(metadata, dict) else None
        imported_at = _parse_timestamp(metadata.get("imported_at")) if isinstance(metadata, dict) else None
        age_days = max(0, (now_utc - observed_at).total_seconds() / 86400) if observed_at else None
        receipt_age = max(0, (now_utc - imported_at).total_seconds() / 86400) if imported_at else None
        if observed_at is None:
            status = "unknown"
        elif age_days > max_age:
            status = "stale"
        elif age_days > max_age * 0.75:
            status = "aging"
        else:
            status = "fresh"
        counts[status] += 1
        fields[field] = {
            "status": status,
            "observed_at": observed_at.isoformat() if observed_at else None,
            "imported_at": imported_at.isoformat() if imported_at else None,
            "observation_age_days": round(age_days, 1) if age_days is not None else None,
            "import_age_days": round(receipt_age, 1) if receipt_age is not None else None,
            "max_age_days": max_age,
            "freshness_basis": "source_observed_at" if observed_at else "unknown",
        }
    return {
        "status": "stale" if counts["stale"] else ("unknown" if counts["unknown"] else ("aging" if counts["aging"] else "fresh")),
        "fields": fields,
        "counts": counts,
        "policy": "A data de importação não substitui a data em que a origem observou o dado.",
    }


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
        # Imports preserve the latest source cell in raw_data. Prefer that cell
        # when present so a blank/invalid refresh cannot silently reuse an older
        # valid database value as if it were current.
        raw_data = _read(source, "raw_data") or {}
        if isinstance(raw_data, dict) and field in raw_data:
            value = raw_data[field]
        reason = None
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(field)
            reason = "missing"
        elif isinstance(value, bool):
            invalid.append(field)
            reason = "boolean_not_numeric"
        else:
            try:
                # Importação brasileira aceita vírgula como separador decimal.
                # O raw_data preserva a célula original, portanto o validador
                # precisa interpretar a mesma convenção que safe_float do importador.
                normalized_value = value.strip().replace(",", ".") if isinstance(value, str) else value
                number = float(normalized_value)
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
    freshness = assess_field_freshness(source)
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
        "freshness": freshness,
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
