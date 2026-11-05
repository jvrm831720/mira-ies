"""Contract for writing feature observations that may feed the predictive model.

Rules:
- Tenant is always provided by the caller from AuthContext / job context — never from client body as authority.
- Only explicitly enabled data sources may write.
- Feature keys must be globally allowlisted and, when configured, source-allowlisted.
- Observations are idempotent by (tenant_id, observation_key).
- This module does not call Composio or connectors; adapters call into it after fetch/transform.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

SourceKind = Literal["native_connector", "composio", "upload", "system"]
ValueType = Literal["number", "text", "boolean", "categorical"]

_FEATURE_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
_SOURCE_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,79}$")

FEATURE_KEY_ALLOWLIST: frozenset[str] = frozenset(
    {
        "dias_atraso_boleto",
        "recorrencia_atrasos",
        "saldo_devedor",
        "status_financeiro",
        "dias_sem_login",
        "presenca_percentual",
        "nota_media",
        "reprovacoes",
        "engagement_score",
        "lms_last_activity_days",
        "lms_submissions_missing",
        "crm_open_tickets",
        "crm_last_contact_days",
        "attendance_rate_30d",
        "grade_trend_30d",
    }
)


class FeatureIngestDenied(RuntimeError):
    """Raised when a source is not authorized to write a feature."""


@dataclass(frozen=True)
class FeatureObservationInput:
    tenant_id: str
    source_kind: SourceKind
    source_key: str
    feature_key: str
    value_type: ValueType
    observed_at: datetime
    student_id: str | None = None
    subject_ref: str | None = None
    value_number: float | None = None
    value_text: str | None = None
    value_boolean: bool | None = None
    reliability: str = "partial"
    payload: dict[str, Any] = field(default_factory=dict)
    observation_key: str | None = None


def normalize_feature_key(raw: str) -> str:
    key = (raw or "").strip().lower().replace("-", "_")
    if not _FEATURE_KEY_RE.match(key):
        raise ValueError(f"feature_key inválido: {raw!r}")
    return key


def normalize_source_key(raw: str) -> str:
    key = (raw or "").strip().lower()
    if not _SOURCE_KEY_RE.match(key):
        raise ValueError(f"source_key inválido: {raw!r}")
    return key


def observation_key_for(
    *,
    tenant_id: str,
    source_kind: str,
    source_key: str,
    feature_key: str,
    student_id: str | None,
    subject_ref: str | None,
    observed_at: datetime,
) -> str:
    """Stable idempotency key using a UTC day bucket across all server timezones."""
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("observed_at deve conter timezone explícito.")
    day = observed_at.astimezone(timezone.utc).strftime("%Y-%m-%d")
    subject = student_id or subject_ref or "unknown"
    material = f"{tenant_id}|{source_kind}|{source_key}|{feature_key}|{subject}|{day}"
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:40]
    return f"obs_{digest}"


def assert_source_may_write_feature(
    *,
    source_enabled: bool,
    allowed_feature_keys: list[str] | None,
    feature_key: str,
    require_global_allowlist: bool = True,
) -> str:
    """Fail closed: disabled source or non-allowlisted feature cannot write."""
    key = normalize_feature_key(feature_key)
    if not source_enabled:
        raise FeatureIngestDenied("Fonte de dados desabilitada para ingestão de features.")
    if require_global_allowlist and key not in FEATURE_KEY_ALLOWLIST:
        raise FeatureIngestDenied(f"feature_key não está na allowlist do modelo: {key}")
    if allowed_feature_keys is not None:
        allowed = {
            normalize_feature_key(item)
            for item in allowed_feature_keys
            if isinstance(item, str)
        }
        if key not in allowed:
            raise FeatureIngestDenied(f"feature_key não autorizada para esta fonte: {key}")
    return key


def validate_observation_values(obs: FeatureObservationInput) -> None:
    if not obs.tenant_id or not str(obs.tenant_id).strip():
        raise ValueError("tenant_id é obrigatório")
    if not obs.source_key or not _SOURCE_KEY_RE.match(obs.source_key):
        raise ValueError("source_key inválido")
    if not obs.student_id and not obs.subject_ref:
        raise ValueError("student_id ou subject_ref é obrigatório")
    if obs.observed_at.tzinfo is None or obs.observed_at.utcoffset() is None:
        raise ValueError("observed_at deve conter timezone explícito.")
    expected_fields = {
        "number": ("value_number", obs.value_number),
        "text": ("value_text", obs.value_text),
        "categorical": ("value_text", obs.value_text),
        "boolean": ("value_boolean", obs.value_boolean),
    }
    if obs.value_type not in expected_fields:
        raise ValueError("value_type inválido")
    required_name, required_value = expected_fields[obs.value_type]
    if required_value is None or (obs.value_type in {"text", "categorical"} and not required_value):
        raise ValueError(f"{required_name} obrigatório para value_type={obs.value_type}")
    other_values = {
        "value_number": obs.value_number,
        "value_text": obs.value_text,
        "value_boolean": obs.value_boolean,
    }
    if any(name != required_name and value is not None for name, value in other_values.items()):
        raise ValueError("Valores incompatíveis com value_type.")
