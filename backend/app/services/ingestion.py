"""Ingestão com normalização, validação e upsert isolado por instituição."""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.student import Student, UploadBatch
from app.services.consent import (
    DEFAULT_COMMUNICATION_PREFERENCES,
    apply_preference_changes,
    record_initial_global_opt_out,
)


COLUMN_ALIASES: dict[str, list[str]] = {
    "matricula": [
        "matricula", "matricula do aluno", "numero de matricula", "número de matrícula",
        "ra", "registro", "registro academico", "codigo aluno", "codigo_aluno",
        "id aluno", "id_aluno", "id matricula", "id matrícula", "student_id", "student id",
        "student number", "enrollment id", "enrollment number", "enrollment_code",
        "registration number", "cod aluno", "rm", "codigo de aluno", "registro do aluno",
    ],
    "nome": [
        "nome", "nome aluno", "nome_aluno", "aluno", "name", "student_name",
        "student name", "nome completo", "nome_completo", "full name",
        "student full name", "display name", "nome completo do aluno", "nome do aluno",
    ],
    "curso": ["curso", "course", "programa", "course_name", "course name", "nome curso", "academic program"],
    "campus": ["campus", "unidade", "unidade de ensino", "unidade academica", "polo", "campus/unidade", "unidade campus", "school campus"],
    "status_aluno": ["status_aluno", "status aluno", "status do aluno", "situacao aluno", "situação aluno", "situacao academica", "situação acadêmica", "student status", "enrollment status"],
    "turma": ["turma", "classe", "class", "class_name", "class name", "codigo turma", "cohort"],
    "semestre": ["semestre", "semestre atual", "periodo", "período", "periodo atual", "periodo letivo", "semester", "current semester", "semestre cursado", "numero do semestre"],
    "forma_ingresso": ["forma_ingresso", "ingresso", "admission", "forma de ingresso", "tipo ingresso", "admission type"],
    "dias_atraso_boleto": [
        "dias_atraso_boleto", "atraso boleto", "dias atraso", "dias em atraso",
        "days overdue", "days_overdue", "overdue days", "atraso", "dias de atraso",
        "dias de atraso financeiro", "dias atraso financeiro", "atraso em dias",
    ],
    "recorrencia_atrasos": [
        "recorrencia_atrasos", "qtd atrasos", "atrasos anteriores", "previous delays",
        "previous_delays", "atrasos", "late payment count", "parcelas em atraso",
        "parcelas vencidas", "quantidade de parcelas vencidas", "qtd parcelas vencidas",
        "numero de parcelas vencidas", "número de parcelas vencidas",
    ],
    "saldo_devedor": [
        "saldo_devedor", "saldo devedor", "debito total", "débito total", "valor em aberto",
        "valor total em atraso", "valor devedor", "debt balance", "outstanding balance",
        "total debt", "debt amount", "total nominal", "debito total r", "debito total rs",
    ],
    "status_financeiro": [
        "status_financeiro", "status financeiro", "status de pagamento", "situacao financeira",
        "situação financeira", "status da cobranca", "status cobrança", "payment status",
        "financial status", "situacao do pagamento", "situação do pagamento",
    ],
    "dias_sem_login": [
        "dias_sem_login", "dias sem acesso", "last_login_days", "last login days",
        "dias inativo", "dias sem moodle", "days inactive", "days since login",
    ],
    "presenca_percentual": [
        "presenca_percentual", "presenca", "frequencia", "attendance",
        "percentual presenca", "freq", "attendance percentage", "attendance_pct",
    ],
    "nota_media": [
        "nota_media", "media", "nota", "average_grade", "average grade",
        "gpa", "media geral", "cr", "grade average",
    ],
    "reprovacoes": ["reprovacoes", "reprovacao", "failures", "qtd reprovacoes", "num reprovacoes", "failed courses"],
    "telefone": [
        "telefone", "celular", "whatsapp", "phone", "phone number",
        "mobile phone", "telefone celular", "contato",
    ],
    "email": ["email", "e_mail", "email_aluno", "e-mail", "email address", "e-mail address", "student email"],
    "communication_opt_out": [
        "communication_opt_out", "comunicacao opt out", "opt_out", "optout",
        "nao_contatar", "não_contatar", "do_not_contact", "do not contact", "dnc",
        "unsubscribed", "marketing opt out",
    ],
}
REQUIRED_COLUMNS = {"matricula", "nome"}
RECOMMENDED_COLUMNS = {
    "dias_atraso_boleto", "dias_sem_login", "presenca_percentual", "nota_media", "semestre",
}
COLUMN_LABELS = {
    "matricula": "Matrícula / RA",
    "nome": "Nome completo",
    "curso": "Curso",
    "campus": "Unidade / Campus",
    "status_aluno": "Status do aluno",
    "turma": "Turma",
    "semestre": "Semestre atual",
    "forma_ingresso": "Forma de ingresso",
    "dias_atraso_boleto": "Dias de atraso financeiro",
    "recorrencia_atrasos": "Parcelas vencidas / recorrência de atrasos",
    "saldo_devedor": "Saldo devedor (R$)",
    "status_financeiro": "Status financeiro",
    "dias_sem_login": "Dias sem acesso ao AVA/LMS",
    "presenca_percentual": "Presença (%)",
    "nota_media": "Nota média",
    "reprovacoes": "Reprovações",
    "telefone": "Telefone / WhatsApp",
    "email": "E-mail",
    "communication_opt_out": "Não contatar (opt-out)",
}
NUMERIC_RULES = {
    "semestre": ("int", 1, 30),
    "dias_atraso_boleto": ("int", 0, 3650),
    "recorrencia_atrasos": ("int", 0, 100),
    "dias_sem_login": ("int", 0, 3650),
    "presenca_percentual": ("float", 0, 100),
    "nota_media": ("float", 0, 10),
    "reprovacoes": ("int", 0, 100),
    "saldo_devedor": ("float", 0, 1000000000),
}
_NORMALIZED_ALIASES: dict[str, set[str]] = {}


def normalize_header(value: Any) -> str:
    """Normaliza cabeçalhos de forma determinística; não usa IA nem serviços externos."""
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.strip().lower().replace("%", " pct ")
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


for _target, _aliases in COLUMN_ALIASES.items():
    _NORMALIZED_ALIASES[_target] = {normalize_header(alias) for alias in _aliases}
    _NORMALIZED_ALIASES[_target].add(normalize_header(_target))


def normalize_columns(
    df: pd.DataFrame,
    column_mapping: dict[str, str] | None = None,
) -> tuple[pd.DataFrame, dict[str, str]]:
    """Retorna dataframe normalizado e mapa cabeçalho -> campo canônico.

    O mapeamento manual substitui a sugestão automática para cabeçalhos presentes
    no dicionário; destino vazio significa ignorar a coluna. Não permite que duas
    colunas alimentem silenciosamente o mesmo campo.
    """
    normalized = df.copy()
    source_headers = [normalize_header(column) for column in normalized.columns]
    if len(set(source_headers)) != len(source_headers):
        raise ValueError("Há cabeçalhos duplicados após normalização. Renomeie as colunas e tente novamente.")
    normalized.columns = source_headers

    manual: dict[str, str] = {}
    if column_mapping is not None:
        for source, target_value in column_mapping.items():
            source_key = normalize_header(source)
            if source_key not in source_headers:
                raise ValueError(f"O cabeçalho mapeado '{source}' não existe no arquivo.")
            target = normalize_header(target_value) if target_value else ""
            if target and target not in COLUMN_ALIASES:
                raise ValueError(f"Campo de destino inválido para '{source}'.")
            manual[source_key] = target

    rename_map: dict[str, str] = {}
    used_targets: set[str] = set()
    explicitly_mapped = set(manual)
    for source, target in manual.items():
        if not target:
            continue
        if target in used_targets:
            raise ValueError(
                f"Mais de uma coluna foi mapeada para '{COLUMN_LABELS[target]}'. "
                "Escolha apenas uma coluna para esse campo."
            )
        rename_map[source] = target
        used_targets.add(target)

    # Sugestões por aliases exatos. Colunas explicitamente ignoradas não são remapeadas.
    for target, aliases in _NORMALIZED_ALIASES.items():
        if target in used_targets:
            continue
        for source in source_headers:
            if source in explicitly_mapped or source in rename_map:
                continue
            if source in aliases:
                rename_map[source] = target
                used_targets.add(target)
                break

    return normalized.rename(columns=rename_map), rename_map


def safe_int(value: Any) -> int | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return int(float(str(value).replace(",", ".")))
    except (ValueError, TypeError, OverflowError):
        return None


def safe_semester(value: Any) -> int | None:
    """Aceita formatos comuns de semestre e mantém o limite aplicado pelo importador."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, bool):
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    # Exemplos válidos: 3, 3.0, 3º, 3o, 3º semestre, semestre 3.
    match = re.fullmatch(
        r"(?:semestre\s*)?(\d+)(?:\.0+)?(?:\s*(?:º|°|o))?(?:\s*semestre)?",
        text,
    )
    if not match:
        return None
    try:
        return int(match.group(1))
    except (ValueError, TypeError, OverflowError):
        return None

def safe_currency(value: Any) -> float | None:
    """Converte valores monetários brasileiros ou numéricos sem confundir separadores."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip().replace("R$", "").replace(" ", "")
    if not text:
        return None
    if "," in text and "." in text:
        # Convenção brasileira: ponto para milhar, vírgula decimal.
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        return float(text)
    except (ValueError, TypeError, OverflowError):
        return None


def safe_float(value: Any) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return float(str(value).replace(",", "."))
    except (ValueError, TypeError, OverflowError):
        return None


def safe_str(value: Any) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    return text or None


def safe_bool(value: Any) -> bool | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "t", "yes", "y", "sim", "s", "on"}:
        return True
    if normalized in {"0", "false", "f", "no", "n", "nao", "não", "off", ""}:
        return False
    return None


def _clamp(value: float | None, lo: float, hi: float) -> float | None:
    if value is None:
        return None
    return max(lo, min(hi, value))


def _clamp_int(value: int | None, lo: int, hi: int) -> int | None:
    if value is None:
        return None
    return int(max(lo, min(hi, value)))


def validate_and_clean_row(row: pd.Series, idx: int) -> tuple[dict | None, list[str]]:
    line_number = idx + 2  # planilha: cabeçalho na linha 1
    warnings: list[str] = []
    matricula = safe_str(row.get("matricula"))
    nome = safe_str(row.get("nome"))
    if not matricula:
        return None, [f"Linha {line_number}: matrícula ausente; registro não será importado."]
    if not nome:
        return None, [f"Linha {line_number}: nome ausente; registro não será importado."]

    for field, (kind, minimum, maximum) in NUMERIC_RULES.items():
        raw_value = safe_str(row.get(field))
        if not raw_value:
            continue
        parsed = safe_int(raw_value) if kind == "int" else (safe_currency(raw_value) if field == "saldo_devedor" else safe_float(raw_value))
        if parsed is None:
            warnings.append(f"Linha {line_number}: valor inválido em '{COLUMN_LABELS[field]}'; o campo será ignorado.")
            continue
        if parsed < minimum or parsed > maximum:
            warnings.append(
                f"Linha {line_number}: '{COLUMN_LABELS[field]}' será limitado ao intervalo {minimum}–{maximum}."
            )

    raw_email = safe_str(row.get("email"))
    email = raw_email
    if raw_email and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", raw_email):
        warnings.append(f"Linha {line_number}: e-mail inválido; o campo ficará vazio nesta importação.")
        email = None

    if safe_str(row.get("communication_opt_out")) and safe_bool(row.get("communication_opt_out")) is None:
        warnings.append(
            f"Linha {line_number}: valor de 'Não contatar' não reconhecido; a preferência existente será preservada."
        )

    data = {
        "matricula": matricula[:50],
        "nome": nome[:255],
        "curso": safe_str(row.get("curso")),
        "campus": (safe_str(row.get("campus")) or "")[:150] or None,
        "status_aluno": (safe_str(row.get("status_aluno")) or "")[:80] or None,
        "turma": safe_str(row.get("turma")),
        "semestre": _clamp_int(safe_semester(row.get("semestre")), 1, 30),
        "forma_ingresso": safe_str(row.get("forma_ingresso")),
        "telefone": (safe_str(row.get("telefone")) or "")[:30] or None,
        "email": (email or "")[:255] or None,
        "communication_opt_out": safe_bool(row.get("communication_opt_out")) if safe_bool(row.get("communication_opt_out")) is not None else False,
        "dias_atraso_boleto": _clamp_int(safe_int(row.get("dias_atraso_boleto")), 0, 3650),
        "recorrencia_atrasos": _clamp_int(safe_int(row.get("recorrencia_atrasos")), 0, 100),
        "saldo_devedor": _clamp(safe_currency(row.get("saldo_devedor")), 0.0, 1000000000.0),
        "status_financeiro": safe_str(row.get("status_financeiro"))[:80] if safe_str(row.get("status_financeiro")) else None,
        "dias_sem_login": _clamp_int(safe_int(row.get("dias_sem_login")), 0, 3650),
        "presenca_percentual": _clamp(safe_float(row.get("presenca_percentual")), 0.0, 100.0),
        "nota_media": _clamp(safe_float(row.get("nota_media")), 0.0, 10.0),
        "reprovacoes": _clamp_int(safe_int(row.get("reprovacoes")), 0, 100),
    }
    return data, warnings


def prepare_import_rows(
    df: pd.DataFrame,
    column_mapping: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Usado tanto pela prévia como pela persistência para manter validação consistente."""
    df_original = df.copy()
    df_normalized, rename_map = normalize_columns(df, column_mapping)
    missing = sorted(REQUIRED_COLUMNS - set(df_normalized.columns))
    errors: list[dict[str, Any]] = []
    warnings: list[str] = []
    cleaned: list[dict[str, Any]] = []

    for index, row in df_normalized.iterrows():
        idx = int(index) if isinstance(index, (int, float)) else len(cleaned)
        data, row_warnings = validate_and_clean_row(row, idx)
        if data is None:
            errors.append({"line": idx + 2, "message": re.sub(r"^Linha \d+:\s*", "", row_warnings[0]) if row_warnings else "Linha inválida.", "severity": "block", "column": "matricula" if not safe_str(row.get("matricula")) else "nome", "action": "Preencha o campo obrigatório ou remova a linha."})
            continue
        warnings.extend(row_warnings)
        raw = {key: (None if pd.isna(value) else value) for key, value in row.to_dict().items()}
        cleaned.append({"data": data, "raw": raw, "line": idx + 2})

    # Dentro do arquivo, conserva a última ocorrência da matrícula, como o fluxo antigo.
    unique: dict[str, dict[str, Any]] = {}
    for item in cleaned:
        unique[item["data"]["matricula"]] = item
    duplicates_removed = len(cleaned) - len(unique)
    if duplicates_removed:
        warnings.append(
            f"{duplicates_removed} linha(s) duplicada(s) por matrícula foram consolidadas; "
            "a última ocorrência será usada."
        )
    cleaned_unique = list(unique.values())

    columns = []
    first_row = df_original.iloc[0] if len(df_original) else None
    for original in df_original.columns:
        key = normalize_header(original)
        sample = safe_str(first_row[original]) if first_row is not None else None
        columns.append({
            "key": key,
            "label": str(original),
            "suggested_field": rename_map.get(key),
            "sample": sample[:80] if sample else "",
        })

    mapped_targets = set(rename_map.values())
    rows_to_import = len(cleaned_unique)
    discarded = len(df_original) - len(cleaned)
    missing_recommended = sorted(RECOMMENDED_COLUMNS - mapped_targets)
    null_rates = {
        col: round(float(df_normalized[col].isna().mean() * 100), 1)
        for col in RECOMMENDED_COLUMNS if col in df_normalized.columns
    }
    coverage = rows_to_import / len(df_original) if len(df_original) else 0
    quality_score = max(0.0, min(100.0, coverage * 100 - len(missing_recommended) * 8))

    sample_fields = [
        "matricula", "nome", "email", "telefone", "curso", "campus", "status_aluno", "turma", "semestre",
        "saldo_devedor", "status_financeiro", "dias_atraso_boleto", "dias_sem_login", "presenca_percentual", "nota_media",
    ]
    sample_rows = []
    for item in cleaned_unique[:6]:
        sample_rows.append({"line": item["line"], **{field: item["data"].get(field) for field in sample_fields}})

    issues = [
        {"line": item["line"], "severity": "block", "column": "matricula" if "matrícula ausente" in item["message"] else "nome", "message": item["message"], "action": "Preencha o campo obrigatório ou remova a linha."}
        for item in errors
    ]
    for warning in warnings:
        match = re.match(r"^Linha (\d+):\s*(.*)$", warning)
        if match:
            message = match.group(2)
            column = next((field for field, label in COLUMN_LABELS.items() if label in message), None)
            issues.append({"line": int(match.group(1)), "severity": "attention", "column": column, "message": message, "action": "Revise o valor; campos inválidos serão ignorados ou normalizados."})
        else:
            issues.append({"line": None, "severity": "info", "column": None, "message": warning, "action": "Confira antes de confirmar."})

    return {
        "columns": columns,
        "mapped_columns": rename_map,
        "required_columns": sorted(REQUIRED_COLUMNS),
        "missing_required_columns": missing,
        "recommended_columns": sorted(RECOMMENDED_COLUMNS),
        "missing_recommended_columns": missing_recommended,
        "rows_received": len(df_original),
        "rows_to_import": rows_to_import,
        "invalid_rows_count": len(errors),
        "invalid_rows": errors[:20],
        "issues": issues[:100],
        "duplicates_in_file": duplicates_removed,
        "sample_rows": sample_rows,
        "warnings": warnings[:30],
        "warnings_total": len(warnings),
        "quality_score": round(quality_score, 1),
        "columns_original": [str(column) for column in df_original.columns],
        "columns_recognized": sorted(mapped_targets),
        "null_rates_pct": null_rates,
        "can_import": not missing and rows_to_import > 0,
        # Internal prepared values consumed by persistence. API removes these keys.
        "_df_normalized": df_normalized,
        "_df_original": df_original,
        "_rename_map": rename_map,
        "_cleaned_rows": cleaned_unique,
        "_rows_discarded": discarded,
        "_warnings": warnings,
    }


def build_quality_report(
    df_original,
    df_normalized,
    rename_map,
    valid_rows,
    discarded,
    warnings,
    duplicates_removed,
) -> dict[str, Any]:
    mapped = set(rename_map.values())
    missing_recommended = sorted(RECOMMENDED_COLUMNS - mapped)
    null_rates = {
        col: round(float(df_normalized[col].isna().mean() * 100), 1)
        for col in RECOMMENDED_COLUMNS if col in df_normalized.columns
    }
    coverage = valid_rows / len(df_original) if len(df_original) else 0
    score = max(0.0, min(100.0, coverage * 100 - len(missing_recommended) * 8))
    return {
        "rows_received": len(df_original),
        "rows_imported": valid_rows,
        "rows_discarded": discarded,
        "duplicates_removed": duplicates_removed,
        "columns_original": [str(column) for column in df_original.columns],
        "columns_mapped": rename_map,
        "columns_recognized": sorted(mapped),
        "missing_recommended_columns": missing_recommended,
        "null_rates_pct": null_rates,
        "warnings": warnings[:30],
        "warnings_total": len(warnings),
        "quality_score": round(score, 1),
    }


async def create_batch_and_students(
    session: AsyncSession,
    *,
    filename: str,
    original_filename: str,
    df: pd.DataFrame,
    tenant_id: str | None = None,
    column_mapping: dict[str, str] | None = None,
    batch_id: str | None = None,
) -> tuple[UploadBatch, list[Student], dict[str, Any]]:
    prepared = prepare_import_rows(df, column_mapping)
    missing = prepared["missing_required_columns"]
    if missing:
        raise ValueError(
            f"Colunas obrigatórias ausentes: {', '.join(missing)}. "
            f"Colunas disponíveis: {prepared['columns_original']}"
        )
    cleaned_rows = prepared["_cleaned_rows"]
    if not cleaned_rows:
        raise ValueError("Nenhuma linha válida encontrada após a validação.")

    df_original = prepared["_df_original"]
    df_normalized = prepared["_df_normalized"]
    rename_map = prepared["_rename_map"]
    all_warnings = prepared["_warnings"]
    duplicates_removed = prepared["duplicates_in_file"]

    batch = UploadBatch(
        id=batch_id,
        filename=filename,
        original_filename=original_filename,
        status="processing",
        total_rows=len(df_original),
        columns=list(df_normalized.columns),
        tenant_id=tenant_id,
    )
    session.add(batch)
    await session.flush()

    matriculas = [item["data"]["matricula"] for item in cleaned_rows]
    existing_by_matricula: dict[str, Student] = {}
    if tenant_id is not None and matriculas:
        query = (
            select(Student)
            .where(Student.tenant_id == tenant_id, Student.matricula.in_(matriculas))
            .order_by(Student.updated_at.desc())
        )
        existing = (await session.execute(query)).scalars().all()
        # Se dados legados já contêm duplicatas, atualiza apenas o registro mais recente.
        for student in existing:
            existing_by_matricula.setdefault(student.matricula, student)

    mapped_targets = set(rename_map.values())
    students: list[Student] = []
    new_students: list[Student] = []
    initial_opt_out_students: list[Student] = []
    rows_created = 0
    rows_updated = 0
    mutable_fields = (
        "nome", "curso", "campus", "status_aluno", "turma", "semestre", "forma_ingresso", "telefone",
        "email", "communication_opt_out", "dias_atraso_boleto", "recorrencia_atrasos", "saldo_devedor", "status_financeiro",
        "dias_sem_login", "presenca_percentual", "nota_media", "reprovacoes",
    )

    for item in cleaned_rows:
        data = item["data"]
        raw = item["raw"]
        existing = existing_by_matricula.get(data["matricula"])
        if existing is not None:
            # Células vazias/ausentes nunca apagam dados existentes; opt-out explícito é respeitado.
            for field in mutable_fields:
                if field not in mapped_targets:
                    continue
                raw_value = raw.get(field)
                if field == "communication_opt_out":
                    parsed_bool = safe_bool(raw_value)
                    if safe_str(raw_value) is not None and parsed_bool is not None and tenant_id:
                        apply_preference_changes(
                            session,
                            tenant_id=tenant_id,
                            student=existing,
                            opt_out=parsed_bool,
                            source="csv_upload",
                            method="import_column",
                            location="student_import",
                            source_reference=batch.id,
                        )
                    continue
                if safe_str(raw_value) is None:
                    continue
                value = data.get(field)
                # Um valor preenchido mas inválido não deve apagar informação já conhecida.
                if value is not None:
                    setattr(existing, field, value)
            existing.batch_id = batch.id
            existing.raw_data = {**(existing.raw_data or {}), **raw}
            students.append(existing)
            rows_updated += 1
        else:
            student = Student(
                batch_id=batch.id,
                tenant_id=tenant_id,
                matricula=data["matricula"],
                nome=data["nome"],
                curso=data.get("curso"),
                campus=data.get("campus"),
                status_aluno=data.get("status_aluno"),
                turma=data.get("turma"),
                semestre=data.get("semestre"),
                forma_ingresso=data.get("forma_ingresso"),
                telefone=data.get("telefone"),
                email=data.get("email"),
                communication_opt_out=False,
                communication_opted_out_at=None,
                communication_preferences={
                    "channels": dict(DEFAULT_COMMUNICATION_PREFERENCES["channels"]),
                    "topics": dict(DEFAULT_COMMUNICATION_PREFERENCES["topics"]),
                },
                dias_atraso_boleto=data.get("dias_atraso_boleto"),
                recorrencia_atrasos=data.get("recorrencia_atrasos"),
                saldo_devedor=data.get("saldo_devedor"),
                status_financeiro=data.get("status_financeiro"),
                dias_sem_login=data.get("dias_sem_login"),
                presenca_percentual=data.get("presenca_percentual"),
                nota_media=data.get("nota_media"),
                reprovacoes=data.get("reprovacoes"),
                raw_data=raw,
            )
            explicit_opt_out = safe_bool(raw.get("communication_opt_out"))
            if explicit_opt_out is True:
                student.communication_opt_out = True
                student.communication_opted_out_at = datetime.now(timezone.utc)
                if tenant_id:
                    initial_opt_out_students.append(student)
            students.append(student)
            new_students.append(student)
            rows_created += 1

    # Existing students are dirty-tracked; only newly created objects need add_all.
    session.add_all(new_students)
    await session.flush()
    for student in initial_opt_out_students:
        record_initial_global_opt_out(
            session,
            tenant_id=tenant_id,
            student=student,
            opt_out=True,
            source="csv_upload",
            method="import_column",
            location="student_import",
            source_reference=batch.id,
        )
    batch.status = "processed"
    batch.processed_rows = len(students)
    batch.processed_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(batch)

    quality = build_quality_report(
        df_original,
        df_normalized,
        rename_map,
        len(students),
        prepared["_rows_discarded"],
        all_warnings,
        duplicates_removed,
    )
    quality["rows_created"] = rows_created
    quality["rows_updated"] = rows_updated
    quality["existing_matches"] = rows_updated
    return batch, students, quality


async def get_batch(
    session: AsyncSession,
    batch_id: str,
    tenant_id: str | None = None,
) -> UploadBatch | None:
    query = select(UploadBatch).where(UploadBatch.id == batch_id)
    if tenant_id:
        query = query.where(UploadBatch.tenant_id == tenant_id)
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def get_students_by_batch(
    session: AsyncSession,
    batch_id: str,
    limit: int = 100,
) -> list[Student]:
    result = await session.execute(
        select(Student).where(Student.batch_id == batch_id).order_by(Student.nome).limit(limit)
    )
    return list(result.scalars().all())
