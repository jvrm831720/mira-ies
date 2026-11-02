"""Semantic mapping for documented JACAD enrollment and financial summary payloads."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any


_FINANCIAL_PRIORITY = {
    "VENCIDO": 0,
    "EM_ABERTO": 1,
    "PAGO": 2,
    "SEM_FINANCEIRO": 3,
}


def _text(value: Any) -> str | None:
    if value is None:
        return None
    result = str(value).strip()
    return result or None


def _date(value: Any) -> date | None:
    raw = _text(value)
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(raw[:10])
        except ValueError:
            return None


def _status(row: dict[str, Any]) -> str | None:
    value = _text(row.get("statusMatricula") or row.get("status"))
    return value.upper() if value else None


def enrich_jacad_students(
    students: list[dict[str, Any]],
    enrollments: list[dict[str, Any]],
    financial_summaries: list[dict[str, Any]],
    *,
    today: date | None = None,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Join on provider IDs/RA and map only fields whose semantics are documented."""
    today = today or date.today()
    by_provider_id: dict[str, dict[str, Any]] = {}
    by_ra: dict[str, dict[str, Any]] = {}
    for row in students:
        provider_id = _text(row.get("idAluno"))
        ra = _text(row.get("ra"))
        if provider_id:
            by_provider_id[provider_id] = row
        if ra:
            by_ra[ra] = row

    enrollment_groups: dict[str, list[dict[str, Any]]] = {}
    for row in enrollments:
        provider_id = _text(row.get("idAluno"))
        ra = _text(row.get("ra"))
        student = by_provider_id.get(provider_id) if provider_id else None
        student = student or (by_ra.get(ra) if ra else None)
        if not student:
            continue
        key = _text(student.get("idAluno")) or _text(student.get("ra")) or ""
        enrollment_groups.setdefault(key, []).append(row)

    finance_groups: dict[str, list[dict[str, Any]]] = {}
    for row in financial_summaries:
        provider_id = _text(row.get("idAluno"))
        ra = _text(row.get("ra"))
        student = by_provider_id.get(provider_id) if provider_id else None
        student = student or (by_ra.get(ra) if ra else None)
        if not student:
            continue
        key = _text(student.get("idAluno")) or _text(student.get("ra")) or ""
        finance_groups.setdefault(key, []).append(row)

    enriched: list[dict[str, Any]] = []
    metadata: dict[str, dict[str, Any]] = {}
    for source in students:
        row = dict(source)
        provider_id = _text(source.get("idAluno"))
        ra = _text(source.get("ra"))
        key = provider_id or ra or ""
        matricula = ra or provider_id
        if not matricula:
            continue

        enrollment_rows = enrollment_groups.get(key, [])
        if enrollment_rows:
            active_first = sorted(
                enrollment_rows,
                key=lambda item: (
                    1 if _status(item) == "ATIVA" else 0,
                    _text(item.get("dataAlteracao")) or "",
                    _text(item.get("idMatricula")) or "",
                ),
                reverse=True,
            )
            selected = active_first[0]
            enrollment_status = _status(selected)
            if enrollment_status:
                row["status_aluno"] = enrollment_status
            if _text(selected.get("curso")):
                row["curso"] = _text(selected.get("curso"))
            if _text(selected.get("turma")):
                row["turma"] = _text(selected.get("turma"))

        summaries = finance_groups.get(key, [])
        active_enrollment_ids = {
            str(item.get("idMatricula")) for item in enrollment_rows
            if _status(item) == "ATIVA" and item.get("idMatricula") is not None
        }
        if active_enrollment_ids:
            active_summaries = [
                item for item in summaries
                if item.get("idMatricula") is not None
                and str(item.get("idMatricula")) in active_enrollment_ids
            ]
            if active_summaries:
                summaries = active_summaries
        selected_finance = None
        if summaries:
            selected_finance = min(
                summaries,
                key=lambda item: _FINANCIAL_PRIORITY.get(
                    (_text(item.get("situacaoFinanceira")) or "").upper(), 99
                ),
            )
            financial_status = _text(selected_finance.get("situacaoFinanceira"))
            if financial_status and financial_status.upper() in _FINANCIAL_PRIORITY:
                financial_status = financial_status.upper()
                row["status_financeiro"] = financial_status
                if financial_status == "VENCIDO":
                    due_date = _date(selected_finance.get("dataVencimentoParcela"))
                    if due_date:
                        row["dias_atraso_boleto"] = max((today - due_date).days, 0)
                elif financial_status in {"EM_ABERTO", "PAGO", "SEM_FINANCEIRO"}:
                    # JACAD defines EM_ABERTO as no overdue open installment.
                    row["dias_atraso_boleto"] = 0
                    row["recorrencia_atrasos"] = 0
                    if financial_status in {"PAGO", "SEM_FINANCEIRO"}:
                        row["saldo_devedor"] = 0.0

        enriched.append(row)
        metadata[matricula] = {
            "id_aluno": provider_id,
            "ra": ra,
            "id_matriculas": sorted({
                str(item.get("idMatricula")) for item in enrollment_rows
                if item.get("idMatricula") is not None
            }),
            "status_matricula": row.get("status_aluno"),
            "financial_summaries": [
                {
                    "id_matricula": item.get("idMatricula"),
                    "situacao_financeira": item.get("situacaoFinanceira"),
                    "status_contrato": item.get("statusContrato"),
                    "contrato_entregue": item.get("contratoEntregue"),
                    "data_vencimento_parcela_aberta": item.get("dataVencimentoParcela"),
                    "valor_parcela_aberta": item.get("valorParcela"),
                }
                for item in summaries
            ],
        }
    return enriched, metadata
