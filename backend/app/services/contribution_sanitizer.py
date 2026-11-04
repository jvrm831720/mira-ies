"""Sanitization pipeline for shared-training contributions.

Removes direct identifiers and high-risk indirect combinations before a
contribution can be marked eligible. The output is a deterministic feature
row list plus a content hash. Personal identifiers never leave this module.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

# Versioned rule set. Bump when allowed feature columns or redaction change.
ANONYMIZATION_RULES_VERSION = "anon-v1"
FEATURE_SCHEMA_VERSION = "features-v1"

# Columns that must never appear in a shared contribution.
FORBIDDEN_KEYS = frozenset({
    "matricula",
    "student_id",
    "nome",
    "name",
    "cpf",
    "email",
    "telefone",
    "phone",
    "rg",
    "endereco",
    "address",
    "tenant_id",
    "batch_id",
    "id",
})

# Allowlist of feature keys permitted in the sanitized payload.
# Anything outside this set is dropped.
ALLOWED_FEATURE_KEYS = frozenset({
    "attendance_rate",
    "grade_avg",
    "credits_completed",
    "credits_enrolled",
    "days_since_last_login",
    "financial_delay_days",
    "risk_score",
    "engagement_score",
    "semester",
    "course_load",
    "label",
    "target_definition",
})


@dataclass(frozen=True)
class SanitizedRow:
    features: dict[str, float | int | str | None]
    label: int | None
    target_definition: str | None


@dataclass(frozen=True)
class SanitizationResult:
    rows: list[SanitizedRow]
    content_hash: str
    anonymization_rules_version: str
    feature_schema_version: str
    rejected: bool
    rejection_reason: str | None


def _strip_forbidden(raw: Mapping[str, Any]) -> dict[str, Any]:
    return {
        k: v
        for k, v in raw.items()
        if k.lower() not in FORBIDDEN_KEYS and k in ALLOWED_FEATURE_KEYS
    }


def _has_reidentification_risk(raw: Mapping[str, Any]) -> str | None:
    """Heuristic checks for residual re-identification risk."""
    lower_keys = {k.lower() for k in raw}
    if lower_keys & {k.lower() for k in FORBIDDEN_KEYS}:
        return "Residual forbidden identifier keys detected."
    # Extremely sparse rows with unique combinations can still re-identify.
    if len(raw) <= 2 and "label" in {k.lower() for k in raw}:
        return "Row too sparse; residual re-identification risk."
    return None


def sanitize_training_rows(
    source_rows: Sequence[Mapping[str, Any]],
    *,
    require_label: bool = True,
) -> SanitizationResult:
    """Sanitize a batch of feature dicts into shareable rows + content hash."""
    if not source_rows:
        return SanitizationResult(
            rows=[],
            content_hash="",
            anonymization_rules_version=ANONYMIZATION_RULES_VERSION,
            feature_schema_version=FEATURE_SCHEMA_VERSION,
            rejected=True,
            rejection_reason="Empty source dataset.",
        )

    sanitized: list[SanitizedRow] = []
    for raw in source_rows:
        risk = _has_reidentification_risk(raw)
        if risk:
            return SanitizationResult(
                rows=[],
                content_hash="",
                anonymization_rules_version=ANONYMIZATION_RULES_VERSION,
                feature_schema_version=FEATURE_SCHEMA_VERSION,
                rejected=True,
                rejection_reason=risk,
            )
        cleaned = _strip_forbidden(raw)
        label_val = cleaned.pop("label", None)
        target_def = cleaned.pop("target_definition", None)
        if require_label and label_val is None:
            return SanitizationResult(
                rows=[],
                content_hash="",
                anonymization_rules_version=ANONYMIZATION_RULES_VERSION,
                feature_schema_version=FEATURE_SCHEMA_VERSION,
                rejected=True,
                rejection_reason="Labeled contribution required; unlabeled row found.",
            )
        if not cleaned:
            return SanitizationResult(
                rows=[],
                content_hash="",
                anonymization_rules_version=ANONYMIZATION_RULES_VERSION,
                feature_schema_version=FEATURE_SCHEMA_VERSION,
                rejected=True,
                rejection_reason="No allowed feature columns remained after sanitization.",
            )
        sanitized.append(
            SanitizedRow(
                features=cleaned,
                label=int(label_val) if label_val is not None else None,
                target_definition=str(target_def) if target_def is not None else None,
            )
        )

    # Deterministic hash over ordered rows.
    payload = [
        {
            "features": dict(sorted(row.features.items())),
            "label": row.label,
            "target_definition": row.target_definition,
        }
        for row in sanitized
    ]
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()

    return SanitizationResult(
        rows=sanitized,
        content_hash=digest,
        anonymization_rules_version=ANONYMIZATION_RULES_VERSION,
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        rejected=False,
        rejection_reason=None,
    )
