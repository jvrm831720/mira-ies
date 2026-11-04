"""Contrato de normalização e dry-run para fixtures sintéticos GVcollege.

Este módulo é puro: não recebe sessão de banco, não faz HTTP e não executa scoring.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from app.services.connectors.gvcollege_discovery import (
    GvcollegeValueType,
    get_synthetic_gvcollege_view,
)


@dataclass(frozen=True)
class GvcollegeIngestionIssue:
    row_number: int
    code: str
    message: str
    severity: str = "error"


@dataclass(frozen=True)
class GvcollegeDryRunRecord:
    tenant_id: str
    source_system: str
    source_view_id: str
    source_schema_version: str
    source_record_id: str
    idempotency_key: str
    observed_at: str | None
    ingested_at: str
    data: dict[str, Any]


@dataclass(frozen=True)
class GvcollegeDryRunReport:
    view_id: str
    tenant_id: str
    rows_received: int
    rows_accepted: int
    rows_rejected: int
    records: tuple[GvcollegeDryRunRecord, ...]
    issues: tuple[GvcollegeIngestionIssue, ...]
    persisted: bool = False
    scoring_executed: bool = False
    remote_requests: int = 0


@dataclass(frozen=True)
class GvcollegeIngestionPreview:
    view_id: str
    schema_version: str
    tenant_id: str
    rows_received: int
    rows_accepted: int
    rows_rejected: int
    acceptance_rate: float
    issue_counts: dict[str, int]
    issues: tuple[GvcollegeIngestionIssue, ...]
    issues_total: int
    issues_truncated: bool
    persisted: bool = False
    scoring_executed: bool = False
    remote_requests: int = 0


def _valid_value(value: Any, value_type: GvcollegeValueType) -> bool:
    if value is None:
        return True
    if value_type == GvcollegeValueType.STRING:
        return isinstance(value, str)
    if value_type == GvcollegeValueType.INTEGER:
        return (
            isinstance(value, int)
            and not isinstance(value, bool)
            and -(2**63) <= value <= (2**63 - 1)
        )
    if value_type == GvcollegeValueType.NUMBER:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return False
        try:
            return math.isfinite(float(value))
        except (OverflowError, ValueError):
            return False
    if value_type == GvcollegeValueType.BOOLEAN:
        return isinstance(value, bool)
    return False


def _iso_timestamp(value: str | None, *, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} deve ser uma string ISO-8601 não vazia")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} inválido: use ISO-8601") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field_name} deve conter fuso horário")
    return parsed.astimezone(timezone.utc).isoformat()


def _idempotency_key(tenant_id: str, view_id: str, schema_version: str, source_record_id: str) -> str:
    material = json.dumps(
        [tenant_id, "gvcollege", view_id, schema_version, source_record_id],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def dry_run_gvcollege_ingestion(
    view_id: str,
    rows: list[dict[str, Any]],
    *,
    tenant_id: str,
    observed_at: str | None = None,
    ingested_at: str | None = None,
) -> GvcollegeDryRunReport:
    """Valida e normaliza registros locais; nenhum efeito externo é possível."""
    if not isinstance(tenant_id, str) or not tenant_id.strip():
        raise ValueError("tenant_id é obrigatório e deve vir do contexto confiável")
    if not isinstance(rows, list):
        raise ValueError("rows deve ser uma lista")
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError("Cada registro deve ser um objeto")
    if len(rows) > 5000:
        raise ValueError("Limite de 5000 registros por dry-run excedido")

    view = get_synthetic_gvcollege_view(view_id)
    normalized_observed_at = _iso_timestamp(observed_at, field_name="observed_at")
    normalized_ingested_at = _iso_timestamp(
        datetime.now(timezone.utc).isoformat() if ingested_at is None else ingested_at,
        field_name="ingested_at",
    )
    field_by_source = {field.source_field: field for field in view.fields}
    records: list[GvcollegeDryRunRecord] = []
    issues: list[GvcollegeIngestionIssue] = []
    seen_ids: set[str] = set()

    for index, row in enumerate(rows, start=1):
        row_issues: list[GvcollegeIngestionIssue] = []
        forbidden_scope_fields = {"tenant_id", "org_id", "organization_id", "institution_id"}
        if forbidden_scope_fields.intersection(row):
            row_issues.append(GvcollegeIngestionIssue(
                index, "tenant_scope_injection",
                "O tenant é definido pelo contexto confiável, nunca pelo registro de origem.",
            ))

        if any(not isinstance(name, str) for name in row):
            row_issues.append(GvcollegeIngestionIssue(
                index, "invalid_source_field_name",
                "Todos os nomes de campos de origem devem ser texto.",
            ))

        unknown_fields = sorted(
            name for name in row
            if isinstance(name, str) and name not in field_by_source
        )
        if unknown_fields:
            row_issues.append(GvcollegeIngestionIssue(
                index, "unknown_source_fields",
                f"Campos não declarados no contrato: {', '.join(unknown_fields)}.",
            ))

        data: dict[str, Any] = {}
        for field in view.fields:
            if field.source_field in row and not field.selectable:
                row_issues.append(GvcollegeIngestionIssue(
                    index, "field_not_selectable",
                    f"Campo não autorizado para ingestão: {field.source_field}.",
                ))
                continue

            value = row.get(field.source_field)
            if value is None and not field.nullable:
                row_issues.append(GvcollegeIngestionIssue(
                    index, "required_field_missing",
                    f"Campo obrigatório ausente: {field.source_field}.",
                ))
                continue
            if (
                isinstance(value, str)
                and not value.strip()
                and not field.nullable
                and field.value_type == GvcollegeValueType.STRING
            ):
                row_issues.append(GvcollegeIngestionIssue(
                    index, "required_field_blank",
                    f"Campo obrigatório não pode ficar vazio: {field.source_field}.",
                ))
                continue
            if not _valid_value(value, field.value_type):
                row_issues.append(GvcollegeIngestionIssue(
                    index, "invalid_field_type",
                    f"Tipo inválido para {field.source_field}; esperado {field.value_type.value}.",
                ))
                continue
            # Ausência permanece None. Nenhum valor favorável é inferido.
            data[field.canonical_field] = value

        source_record_id = row.get(view.pagination_key)
        if not isinstance(source_record_id, str) or not source_record_id.strip():
            row_issues.append(GvcollegeIngestionIssue(
                index, "invalid_source_record_id",
                f"Chave de origem inválida: {view.pagination_key}.",
            ))
            source_record_id = None
        elif source_record_id in seen_ids:
            row_issues.append(GvcollegeIngestionIssue(
                index, "duplicate_source_record_id",
                "Chave de origem duplicada no lote.",
            ))

        if row_issues:
            issues.extend(row_issues)
            continue

        # Uma linha rejeitada por outro motivo não deve bloquear uma linha
        # posterior válida que use a mesma chave de origem.
        seen_ids.add(source_record_id)
        records.append(GvcollegeDryRunRecord(
            tenant_id=tenant_id.strip(),
            source_system="gvcollege",
            source_view_id=view.view_id,
            source_schema_version=view.schema_version,
            source_record_id=source_record_id,
            idempotency_key=_idempotency_key(
                tenant_id.strip(), view.view_id, view.schema_version, source_record_id
            ),
            observed_at=normalized_observed_at,
            ingested_at=normalized_ingested_at,
            data=data,
        ))

    return GvcollegeDryRunReport(
        view_id=view.view_id,
        tenant_id=tenant_id.strip(),
        rows_received=len(rows),
        rows_accepted=len(records),
        rows_rejected=len(rows) - len(records),
        records=tuple(records),
        issues=tuple(issues),
    )


def build_gvcollege_ingestion_preview(
    report: GvcollegeDryRunReport,
    *,
    max_issue_details: int = 200,
) -> GvcollegeIngestionPreview:
    """Gera resumo sem expor valores de alunos ou payloads de origem."""
    if not isinstance(max_issue_details, int) or isinstance(max_issue_details, bool):
        raise ValueError("max_issue_details deve ser um inteiro")
    if not 0 <= max_issue_details <= 1000:
        raise ValueError("max_issue_details deve estar entre 0 e 1000")

    view = get_synthetic_gvcollege_view(report.view_id)
    counts = Counter(issue.code for issue in report.issues)
    total = len(report.issues)
    acceptance_rate = (
        report.rows_accepted / report.rows_received
        if report.rows_received
        else 0.0
    )
    return GvcollegeIngestionPreview(
        view_id=report.view_id,
        schema_version=view.schema_version,
        tenant_id=report.tenant_id,
        rows_received=report.rows_received,
        rows_accepted=report.rows_accepted,
        rows_rejected=report.rows_rejected,
        acceptance_rate=round(acceptance_rate, 4),
        issue_counts=dict(sorted(counts.items())),
        issues=report.issues[:max_issue_details],
        issues_total=total,
        issues_truncated=total > max_issue_details,
        persisted=report.persisted,
        scoring_executed=report.scoring_executed,
        remote_requests=report.remote_requests,
    )


def dry_run_report_to_dict(report: GvcollegeDryRunReport) -> dict[str, Any]:
    """Serialização explícita para testes e futuras interfaces de prévia."""
    return {
        **asdict(report),
        "records": [asdict(record) for record in report.records],
        "issues": [asdict(issue) for issue in report.issues],
    }


def ingestion_preview_to_dict(preview: GvcollegeIngestionPreview) -> dict[str, Any]:
    """Serialização da prévia sem registros normalizados nem valores pessoais."""
    return {
        **asdict(preview),
        "issues": [asdict(issue) for issue in preview.issues],
    }
