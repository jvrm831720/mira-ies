"""
Conector generico — JSON canonico do Beacon.
"""

from __future__ import annotations

from typing import Any

from app.services.connectors.base import (
    ConnectorInfo,
    CANONICAL_FIELDS,
    pick,
    to_int,
    to_float,
    to_bool,
    to_str,
    extract_field_provenance,
)


class GenericConnector:
    info = ConnectorInfo(
        id="generic",
        name="JSON Canonico (Generico)",
        category="generic",
        description=(
            "Aceita array de alunos no schema interno do Beacon. "
            "Use para legados, ETL proprio ou qualquer sistema sem conector dedicado."
        ),
        has_api=True,
        endpoints=[
            "POST /api/v1/connectors/generic/students",
            "POST /api/v1/ingest/students",
        ],
        sample_fields=CANONICAL_FIELDS,
    )

    def transform(self, payload: Any) -> list[dict[str, Any]]:
        if payload is None:
            return []
        if isinstance(payload, dict):
            if "students" in payload:
                items = payload["students"]
            elif "data" in payload:
                items = payload["data"]
            elif "alunos" in payload:
                items = payload["alunos"]
            else:
                items = [payload]
        elif isinstance(payload, list):
            items = payload
        else:
            return []

        records = []
        for item in items:
            if not isinstance(item, dict):
                continue
            matricula = to_str(pick(item, "matricula", "ra", "id", "student_id"))
            nome = to_str(pick(item, "nome", "name", "student_name"))
            if not matricula or not nome:
                continue
            records.append({
                "matricula": matricula,
                "nome": nome,
                "curso": to_str(pick(item, "curso", "course")),
                "turma": to_str(pick(item, "turma", "class", "class_name")),
                "semestre": to_int(pick(item, "semestre", "semester", "period")),
                "forma_ingresso": to_str(pick(item, "forma_ingresso", "admission")),
                "telefone": to_str(pick(item, "telefone", "celular", "whatsapp", "phone")),
                "email": to_str(pick(item, "email", "e_mail")),
                "communication_opt_out": to_bool(
                    pick(item, "communication_opt_out", "comunicacao_opt_out", "opt_out", "optout", "nao_contatar", "não_contatar", "do_not_contact", "dnc"),
                ),
                "dias_atraso_boleto": to_int(pick(item, "dias_atraso_boleto", "days_overdue")),
                "recorrencia_atrasos": to_int(pick(item, "recorrencia_atrasos", "overdue_count")),
                "dias_sem_login": to_int(pick(item, "dias_sem_login", "days_inactive")),
                "presenca_percentual": to_float(pick(item, "presenca_percentual", "attendance")),
                "nota_media": to_float(pick(item, "nota_media", "grade_avg", "gpa")),
                "reprovacoes": to_int(pick(item, "reprovacoes", "failures")),
                "source_id": to_str(pick(item, "source_id", "source"), "generic"),
                "__mira_provenance": extract_field_provenance(item, "generic"),
                "raw": item,
            })
        return records
