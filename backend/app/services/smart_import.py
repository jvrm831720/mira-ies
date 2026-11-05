"""Motor de importação inteligente (dry-run + upsert + mapeamento fuzzy).

Replicar a engrenagem Data Import + Metadata do Frappe, adaptada à stack:
- Mapeamento de-para sugerido por fuzzy matching (aliases exatos primeiro).
- Pré-validação linha a linha em memória, sem inserir nada (dry-run).
- Upsert híbrido por chave de negócio (default: matricula).
- Campos não canônicos alimentam students.custom_fields (JSONB), validados
  pelas definições do tenant em custom_field_definitions.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4
from difflib import SequenceMatcher
from typing import Any, Optional

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.student import Student, UploadBatch
from app.services.custom_fields import coerce_value
from app.services.consent import apply_preference_changes

# Tipos canônicos do cadastro. Aliases vêm de app.services.ingestion.COLUMN_ALIASES
# quando disponíveis (mesma fonte do upload legado) e são enriquecidos por tenant.
STANDARD_FIELD_TYPES: dict[str, str] = {
    "matricula": "text",
    "nome": "text",
    "curso": "text",
    "campus": "text",
    "status_aluno": "text",
    "turma": "text",
    "semestre": "integer",
    "forma_ingresso": "text",
    "telefone": "text",
    "email": "text",
    "communication_opt_out": "boolean",
    "dias_atraso_boleto": "integer",
    "recorrencia_atrasos": "integer",
    "saldo_devedor": "number",
    "status_financeiro": "text",
    "dias_sem_login": "integer",
    "presenca_percentual": "number",
    "nota_media": "number",
    "reprovacoes": "integer",
}

FIELD_MAX_LENGTH: dict[str, int] = {
    "matricula": 50, "nome": 255, "curso": 150, "campus": 150,
    "status_aluno": 80, "turma": 100, "forma_ingresso": 100,
    "telefone": 30, "email": 255, "status_financeiro": 80,
}

DEFAULT_KEY_FIELD = "matricula"

AUTO_ACCEPT_THRESHOLD = 0.85   # mapeia automaticamente
SUGGEST_THRESHOLD = 0.55       # exige confirmação humana
MAX_ROW_ERRORS_RETURNED = 100


# ---------------------------------------------------------------------------
# Fuzzy matching de cabeçalhos
# ---------------------------------------------------------------------------

def normalize_header(value: Any) -> str:
    import re
    import unicodedata

    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _alias_index(catalog: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for entry in catalog:
        keys = {entry["field"], *entry.get("aliases", [])}
        for key in keys:
            normalized = normalize_header(key)
            if normalized and normalized not in index:
                index[normalized] = entry
    return index


def suggest_mapping(headers: list[str], catalog: list[dict[str, Any]]):
    """Retorna (mapping, suggestions, unmapped).

    mapping: header -> {"field", "label", "source", "confidence"} (aceito)
    suggestions: header -> [{"field", "label", "confidence"}] (precisa de confirmação)
    unmapped: headers sem candidato acima de SUGGEST_THRESHOLD
    """
    alias_index = _alias_index(catalog)
    index_keys = sorted(alias_index.keys())
    mapping: dict[str, dict[str, Any]] = {}
    suggestions: dict[str, list[dict[str, Any]]] = {}
    unmapped: list[str] = []

    for header in headers:
        normalized = normalize_header(header)
        exact = alias_index.get(normalized)
        if exact is not None:
            mapping[header] = {
                "field": exact["field"], "label": exact["label"],
                "source": exact["source"], "confidence": 1.0,
            }
            continue
        header_tokens = set(normalized.split())
        candidates = []
        for key in index_keys:
            score = SequenceMatcher(None, normalized, key).ratio()
            # Contenção de tokens estilo token-set: "polo de apoio presencial"
            # casa com o campo "polo de apoio" (e com o alias "polo").
            key_tokens = set(key.split())
            if key_tokens and key_tokens.issubset(header_tokens):
                score = max(score, 0.95)
            if score >= SUGGEST_THRESHOLD:
                entry = alias_index[key]
                candidates.append({
                    "field": entry["field"], "label": entry["label"],
                    "source": entry["source"], "confidence": round(score, 3),
                })
        candidates.sort(key=lambda item: item["confidence"], reverse=True)
        if candidates and candidates[0]["confidence"] >= AUTO_ACCEPT_THRESHOLD:
            mapping[header] = candidates[0]
        elif candidates:
            suggestions[header] = candidates[:3]
        else:
            unmapped.append(header)

    # Impede que duas colunas alimentem silenciosamente o mesmo campo.
    accepted_fields: dict[str, str] = {}
    for header in headers:
        item = mapping.get(header)
        if item is None:
            continue
        field = item["field"]
        previous = accepted_fields.get(field)
        if previous is None:
            accepted_fields[field] = header
        elif item["confidence"] > mapping[previous]["confidence"]:
            suggestions[previous] = [mapping.pop(previous)]
            accepted_fields[field] = header
        else:
            suggestions[header] = [mapping.pop(header)]
    return mapping, suggestions, unmapped


# ---------------------------------------------------------------------------
# Validação linha a linha (dry-run, sem escrita)
# ---------------------------------------------------------------------------

def build_catalog_by_field(
    tenant_catalog: list[dict[str, Any]],
    canonical_aliases: Optional[dict[str, list[str]]] = None,
) -> list[dict[str, Any]]:
    catalog: list[dict[str, Any]] = []
    for field, data_type in STANDARD_FIELD_TYPES.items():
        catalog.append({
            "field": field,
            "label": field.replace("_", " "),
            "aliases": (canonical_aliases or {}).get(field, []),
            "source": "standard",
            "data_type": data_type,
            "options": [],
            "required": field == "matricula",
            "is_pii": field in {"telefone", "email"},
        })
    catalog.extend(tenant_catalog)
    return catalog


def validate_records(
    df: pd.DataFrame,
    mapping: dict[str, dict[str, Any]],
    catalog_by_field: dict[str, dict[str, Any]],
    key_field: str = DEFAULT_KEY_FIELD,
) -> dict[str, Any]:
    """Validate every row, rejecting erroneous rows rather than silently partially importing."""
    if key_field != DEFAULT_KEY_FIELD:
        raise ValueError("Apenas 'matricula' pode ser usada como chave.")
    key_headers = [h for h, target in mapping.items() if target["field"] == key_field]
    if len(key_headers) != 1:
        raise ValueError("Mapeie exatamente uma coluna para a matrícula.")
    key_header = key_headers[0]
    records: list[dict[str, Any]] = []
    row_errors: list[dict[str, Any]] = []
    seen_keys: dict[str, int] = {}
    invalid_rows = duplicates = 0

    for index, (_, row) in enumerate(df.iterrows()):
        row_number = index + 2
        key_raw = row.get(key_header)
        key = str(key_raw).strip() if key_raw is not None else ""
        if not key or key.lower() == "nan":
            invalid_rows += 1
            row_errors.append({"row": row_number, "field": key_field, "message": "Chave ausente."})
            continue
        if len(key) > 50:
            invalid_rows += 1
            row_errors.append({"row": row_number, "field": key_field, "message": "Matrícula excede 50 caracteres."})
            continue
        if key in seen_keys:
            invalid_rows += 1
            duplicates += 1
            row_errors.append({
                "row": row_number, "field": key_field,
                "message": f"Chave duplicada (primeira ocorrência na linha {seen_keys[key]}); linha ignorada.",
            })
            continue
        seen_keys[key] = row_number

        standard: dict[str, Any] = {}
        custom: dict[str, Any] = {}
        has_error = False
        for header, target in mapping.items():
            if header == key_header:
                continue
            entry = catalog_by_field[target["field"]]
            ok, value, error = coerce_value(row.get(header), entry["data_type"], entry.get("options"))
            if ok and value is not None and entry["source"] == "standard":
                max_length = FIELD_MAX_LENGTH.get(entry["field"])
                if max_length is not None and len(str(value)) > max_length:
                    ok, error = False, f"Valor excede {max_length} caracteres."
            if ok and value is None and entry.get("required"):
                ok, error = False, "Campo obrigatório sem valor."
            if not ok:
                has_error = True
                row_errors.append({"row": row_number, "field": target["field"], "header": header, "message": error})
                continue
            if value is not None:
                (custom if entry["source"] == "custom" else standard)[entry["field"]] = value
        if has_error:
            invalid_rows += 1
            continue
        records.append({
            "row": row_number, "key": key, "standard": standard,
            "custom": custom,
            "raw": {str(h): ("" if pd.isna(row.get(h)) else str(row.get(h))) for h in mapping},
        })

    return {
        "records": records,
        "row_errors": row_errors[:MAX_ROW_ERRORS_RETURNED],
        "key_stats": {"valid": len(records), "invalid": invalid_rows, "duplicates": duplicates},
    }


# ---------------------------------------------------------------------------
# Upsert (INSERT de novos + UPDATE de existentes, idempotente por batch)
# ---------------------------------------------------------------------------

async def apply_smart_import(
    db: AsyncSession,
    *,
    tenant_id: str,
    batch_id: str,
    filename: str,
    original_filename: str,
    validated: dict[str, Any],
    mapping: dict[str, dict[str, Any]],
    key_field: str = DEFAULT_KEY_FIELD,
    fingerprint: str | None = None,
) -> dict[str, Any]:
    records: list[dict[str, Any]] = validated["records"]
    if not records:
        raise ValueError("Nenhuma linha válida para importar.")
    keys = [r["key"] for r in records]
    existing_result = await db.execute(
        select(Student).where(Student.tenant_id == tenant_id, Student.matricula.in_(keys))
    )
    existing_by_key = {}
    for student in existing_result.scalars().all():
        if student.matricula in existing_by_key:
            raise ValueError(f"Matrícula {student.matricula} possui registros ambíguos neste tenant.")
        existing_by_key[student.matricula] = student

    if not any(r["key"] in existing_by_key or r["standard"].get("nome") for r in records):
        raise ValueError("Nenhuma linha importável: alunos novos precisam de nome.")
    now = datetime.now(timezone.utc)
    batch = UploadBatch(
        id=batch_id, tenant_id=tenant_id,
        filename=filename, original_filename=original_filename,
        status="processed", total_rows=len(records) + validated["key_stats"]["invalid"], processed_rows=0,
        columns={"mode": "smart_import", "key_field": key_field, "fingerprint": fingerprint,
                 "mapping": {h: m["field"] for h, m in mapping.items()}},
        processed_at=now,
    )
    db.add(batch)

    created = updated = 0
    rejected = validated["key_stats"]["invalid"]
    rejected_rows: list[dict[str, Any]] = []
    for record in records:
        student = existing_by_key.get(record["key"])
        if student is None and not record["standard"].get("nome"):
            rejected += 1
            rejected_rows.append({"row": record["row"], "key": record["key"],
                                  "message": "Aluno novo sem nome; inclua a coluna 'nome' ou importe a base de cadastro primeiro."})
            continue
        if student is None:
            student = Student(
                id=str(uuid4()), tenant_id=tenant_id, batch_id=batch_id,
                matricula=record["key"], nome=record["standard"].pop("nome"),
                custom_fields={},
            )
            # Persist the new student before recording opt-out audit events.
            # The audit table has a student_id FK and the ORM does not infer
            # insertion order from the application-side call sequence.
            db.add(student)
            await db.flush()
            created += 1
        else:
            updated += 1
            # A associação acompanha a importação mais recente para permitir
            # auditoria/status e reavaliação de risco do registro atualizado.
            student.batch_id = batch_id
        for field, value in record["standard"].items():
            if field == "communication_opt_out":
                # Importação não representa consentimento. Somente opt-out afirmativo.
                if value:
                    apply_preference_changes(
                        db, tenant_id=tenant_id, student=student,
                        opt_out=True, source="smart_import", method="csv_upload",
                        location="/api/v1/import/apply", source_reference=batch_id,
                        occurred_at=now,
                    )
                continue
            if hasattr(student, field):
                setattr(student, field, value)
        if record["custom"]:
            merged = {**(student.custom_fields or {}), **record["custom"]}
            student.custom_fields = merged
        student.raw_data = record["raw"]
        student.updated_at = now
        db.add(student)

    batch.processed_rows = created + updated
    batch.columns = {
        **(batch.columns or {}),
        "result_summary": {"created": created, "updated": updated, "rejected": rejected,
                           "rejected_rows": rejected_rows[:50],
                           "row_errors": validated["row_errors"]},
    }
    await db.commit()
    return {
        "batch": batch, "created": created, "updated": updated,
        "rejected": rejected, "rejected_rows": rejected_rows[:50],
        "row_errors": validated["row_errors"],
    }