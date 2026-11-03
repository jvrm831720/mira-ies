"""Conservative SophiA payload normalization.

Unknown, absent and sentinel values remain unknown. This module does not infer
financial balance, delinquency, attendance, risk or aggregate academic scores.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any


def _source_value(record: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in record:
            return record[key]
    return None


def _decimal_or_unknown(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    raw = str(value).strip()
    if not raw or raw in {"-1", "-1,0", "-1.0", "-1,00"}:
        return None
    normalized = raw.replace(".", "").replace(",", ".") if "," in raw else raw
    try:
        parsed = Decimal(normalized)
    except InvalidOperation:
        return None
    if not parsed.is_finite() or parsed < 0:
        return None
    return format(parsed, "f")


def normalize_sophia_resource(resource: str, payload: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return a lossless raw+canonical envelope for each source record."""
    if resource not in {"finance", "report_card", "recent_grades"}:
        raise ValueError("Unsupported SophiA resource.")
    normalized_records: list[dict[str, Any]] = []
    for raw in payload:
        if not isinstance(raw, dict):
            raise ValueError("SophiA source collection contains a non-object.")
        if resource == "finance":
            canonical = {
                "title_id": _source_value(raw, "IdTitulo", "idTitulo"),
                "description": _source_value(raw, "Descricao", "Descrição"),
                "due_date_source": _source_value(raw, "DataVcto", "DataVencimento"),
                "payment_date_source": _source_value(raw, "DataPagamento"),
                "expected_amount_source": _source_value(raw, "ValorPrevisto"),
                "paid_amount_source": _source_value(raw, "ValorPago"),
                "paid_flag_source": _source_value(raw, "Pago"),
                "financial_state": "unknown",
                "outstanding_balance": None,
            }
        else:
            grade_value = _source_value(raw, "Nota", "Media", "Média")
            canonical = {
                "grade_value": _decimal_or_unknown(grade_value),
                "grade_value_known": _decimal_or_unknown(grade_value) is not None,
                "subject_source": _source_value(raw, "Disciplina", "NomeDisciplina"),
                "assessment_source": _source_value(raw, "Etapa", "Avaliacao", "NomeAvaliacao"),
                "class_average": _decimal_or_unknown(_source_value(raw, "MediaTurma")),
            }
        normalized_records.append({"raw": raw, "normalized": canonical})
    return normalized_records
