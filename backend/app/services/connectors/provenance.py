"""Relatórios de cobertura da proveniência por tenant e campo."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.services.connectors.base import PREDICTIVE_SOURCE_FIELDS


def _parse_observed_at(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return None
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def build_provenance_coverage(
    raw_data_rows: list[dict[str, Any] | None],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Conta timestamps explícitos, válidos e não futuros por campo.

    Não considera source_updated_at, imported_at ou timestamps de eventos
    como evidência de observação do campo.
    """
    now_utc = now or datetime.now(timezone.utc)
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    else:
        now_utc = now_utc.astimezone(timezone.utc)

    fields: dict[str, dict[str, Any]] = {}
    total_observations = len(raw_data_rows) * len(PREDICTIVE_SOURCE_FIELDS)
    total_valid = 0
    total_invalid = 0

    for field in sorted(PREDICTIVE_SOURCE_FIELDS):
        valid = 0
        missing = 0
        invalid_or_future = 0
        for raw_data in raw_data_rows:
            provenance = raw_data.get("_mira_provenance", {}) if isinstance(raw_data, dict) else {}
            metadata = provenance.get(field, {}) if isinstance(provenance, dict) else {}
            value = metadata.get("observed_at") if isinstance(metadata, dict) else None
            if value is None or value == "":
                missing += 1
                continue
            parsed = _parse_observed_at(value)
            if parsed is None or parsed > now_utc:
                invalid_or_future += 1
                continue
            valid += 1

        total_valid += valid
        total_invalid += invalid_or_future
        total = len(raw_data_rows)
        fields[field] = {
            "records_total": total,
            "observed_at_valid": valid,
            "missing": missing,
            "invalid_or_future": invalid_or_future,
            "coverage_pct": round(valid / total * 100, 1) if total else 0.0,
        }

    return {
        "records_total": len(raw_data_rows),
        "predictive_fields": len(PREDICTIVE_SOURCE_FIELDS),
        "observations_total": total_observations,
        "observations_with_valid_timestamp": total_valid,
        "observations_missing": total_observations - total_valid - total_invalid,
        "observations_invalid_or_future": total_invalid,
        "coverage_pct": round(total_valid / total_observations * 100, 1) if total_observations else 0.0,
        "fields": fields,
        "policy": "Somente observed_at explícito, válido e não futuro conta como cobertura.",
    }
