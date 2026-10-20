"""Servico de ingestao — normalizacao, qualidade, persistencia com tenant_id."""

from __future__ import annotations

from typing import Any
from datetime import datetime, timezone
import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.student import UploadBatch, Student

COLUMN_ALIASES: dict[str, list[str]] = {
    "matricula": ["matricula", "ra", "registro", "codigo_aluno", "id_aluno", "student_id", "cod_aluno", "rm"],
    "nome": ["nome", "nome_aluno", "aluno", "name", "student_name", "nome_completo"],
    "curso": ["curso", "course", "programa", "course_name", "nome_curso"],
    "turma": ["turma", "classe", "class", "class_name", "codigo_turma"],
    "semestre": ["semestre", "periodo", "semester", "period", "periodo_atual"],
    "forma_ingresso": ["forma_ingresso", "ingresso", "admission", "forma_de_ingresso", "tipo_ingresso"],
    "dias_atraso_boleto": ["dias_atraso_boleto", "atraso_boleto", "dias_atraso", "dias_em_atraso", "days_overdue", "atraso"],
    "recorrencia_atrasos": ["recorrencia_atrasos", "qtd_atrasos", "atrasos_anteriores", "previous_delays", "atrasos"],
    "dias_sem_login": ["dias_sem_login", "dias_sem_acesso", "last_login_days", "dias_inativo", "dias_sem_moodle"],
    "presenca_percentual": ["presenca_percentual", "presenca", "frequencia", "attendance", "percentual_presenca", "freq"],
    "nota_media": ["nota_media", "media", "nota", "average_grade", "gpa", "media_geral", "cr"],
    "reprovacoes": ["reprovacoes", "reprovacao", "failures", "qtd_reprovacoes", "num_reprovacoes"],
    "telefone": ["telefone", "celular", "whatsapp", "phone", "telefone_celular", "contato"],
    "email": ["email", "e_mail", "email_aluno"],
}
REQUIRED_COLUMNS = {"matricula", "nome"}
RECOMMENDED_COLUMNS = {"dias_atraso_boleto", "dias_sem_login", "presenca_percentual", "nota_media", "semestre"}


def normalize_columns(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, str]]:
    df = df.copy()
    df.columns = [str(c).strip().lower().replace(" ", "_").replace("%", "pct").replace("-", "_") for c in df.columns]
    rename_map: dict[str, str] = {}
    used_targets: set[str] = set()
    for target, aliases in COLUMN_ALIASES.items():
        for col in df.columns:
            if col in aliases and target not in used_targets:
                rename_map[col] = target
                used_targets.add(target)
                break
    return df.rename(columns=rename_map), rename_map


def safe_int(value: Any) -> int | None:
    if value is None or (isinstance(value, float) and pd.isna(value)): return None
    try: return int(float(str(value).replace(",", ".")))
    except (ValueError, TypeError): return None

def safe_float(value: Any) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)): return None
    try: return float(str(value).replace(",", "."))
    except (ValueError, TypeError): return None

def safe_str(value: Any) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)): return None
    s = str(value).strip()
    return s or None

def _clamp(value: float | None, lo: float, hi: float) -> float | None:
    if value is None: return None
    return max(lo, min(hi, value))


def _clamp_int(value: int | None, lo: int, hi: int) -> int | None:
    if value is None: return None
    return int(max(lo, min(hi, value)))


def validate_and_clean_row(row: pd.Series, idx: int) -> tuple[dict | None, list[str]]:
    warnings: list[str] = []
    matricula = safe_str(row.get("matricula"))
    nome = safe_str(row.get("nome"))
    if not matricula: return None, [f"Linha {idx + 1}: matricula ausente — descartada"]
    if not nome: return None, [f"Linha {idx + 1}: nome ausente — descartado"]
    data = {
        "matricula": matricula[:50], "nome": nome[:255],
        "curso": safe_str(row.get("curso")), "turma": safe_str(row.get("turma")),
        "semestre": _clamp_int(safe_int(row.get("semestre")), 1, 30),
        "forma_ingresso": safe_str(row.get("forma_ingresso")),
        "telefone": (safe_str(row.get("telefone")) or "")[:30] or None,
        "email": (safe_str(row.get("email")) or "")[:255] or None,
        "dias_atraso_boleto": _clamp_int(safe_int(row.get("dias_atraso_boleto")), 0, 3650),
        "recorrencia_atrasos": _clamp_int(safe_int(row.get("recorrencia_atrasos")), 0, 100),
        "dias_sem_login": _clamp_int(safe_int(row.get("dias_sem_login")), 0, 3650),
        "presenca_percentual": _clamp(safe_float(row.get("presenca_percentual")), 0.0, 100.0),
        "nota_media": _clamp(safe_float(row.get("nota_media")), 0.0, 10.0),
        "reprovacoes": _clamp_int(safe_int(row.get("reprovacoes")), 0, 100),
    }
    return data, warnings


def build_quality_report(df_original, df_normalized, rename_map, valid_rows, discarded, warnings, duplicates_removed) -> dict[str, Any]:
    mapped = set(rename_map.values())
    missing_recommended = sorted(RECOMMENDED_COLUMNS - mapped)
    null_rates = {col: round(float(df_normalized[col].isna().mean() * 100), 1) for col in RECOMMENDED_COLUMNS if col in df_normalized.columns}
    coverage = valid_rows / len(df_original) if len(df_original) else 0
    score = max(0.0, min(100.0, coverage * 100 - len(missing_recommended) * 8))
    return {"rows_received": len(df_original), "rows_imported": valid_rows, "rows_discarded": discarded,
            "duplicates_removed": duplicates_removed, "columns_original": list(df_original.columns),
            "columns_mapped": rename_map, "columns_recognized": sorted(mapped),
            "missing_recommended_columns": missing_recommended, "null_rates_pct": null_rates,
            "warnings": warnings[:30], "warnings_total": len(warnings), "quality_score": round(score, 1)}


async def create_batch_and_students(
    session: AsyncSession, *, filename: str, original_filename: str, df: pd.DataFrame,
    tenant_id: str | None = None,
) -> tuple[UploadBatch, list[Student], dict[str, Any]]:
    df_original = df.copy()
    df_norm, rename_map = normalize_columns(df)
    missing = REQUIRED_COLUMNS - set(df_norm.columns)
    if missing:
        raise ValueError(f"Colunas obrigatorias ausentes: {', '.join(sorted(missing))}. Colunas: {list(df_original.columns)}")
    all_warnings: list[str] = []
    cleaned_rows: list[dict] = []
    for idx, row in df_norm.iterrows():
        data, warns = validate_and_clean_row(row, int(idx) if isinstance(idx, (int, float)) else 0)
        all_warnings.extend(warns)
        if data is not None:
            data["_raw"] = {k: (None if pd.isna(v) else v) for k, v in row.to_dict().items()}
            cleaned_rows.append(data)
    seen: dict[str, dict] = {}
    for row in cleaned_rows:
        seen[row["matricula"]] = row
    duplicates_removed = len(cleaned_rows) - len(seen)
    cleaned_rows = list(seen.values())
    if not cleaned_rows:
        raise ValueError("Nenhuma linha valida encontrada apos validacao.")
    batch = UploadBatch(filename=filename, original_filename=original_filename, status="processing",
                        total_rows=len(df_original), columns=list(df_norm.columns), tenant_id=tenant_id)
    session.add(batch)
    await session.flush()
    students: list[Student] = []
    for data in cleaned_rows:
        raw = data.pop("_raw", {})
        students.append(Student(
            batch_id=batch.id, tenant_id=tenant_id, matricula=data["matricula"], nome=data["nome"],
            curso=data.get("curso"), turma=data.get("turma"), semestre=data.get("semestre"),
            forma_ingresso=data.get("forma_ingresso"), telefone=data.get("telefone"), email=data.get("email"),
            dias_atraso_boleto=data.get("dias_atraso_boleto"),
            recorrencia_atrasos=data.get("recorrencia_atrasos"), dias_sem_login=data.get("dias_sem_login"),
            presenca_percentual=data.get("presenca_percentual"), nota_media=data.get("nota_media"),
            reprovacoes=data.get("reprovacoes"), raw_data=raw,
        ))
    session.add_all(students)
    batch.status = "processed"
    batch.processed_rows = len(students)
    batch.processed_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(batch)
    quality = build_quality_report(df_original, df_norm, rename_map, len(students),
        len(df_original) - len(cleaned_rows) - duplicates_removed, all_warnings, duplicates_removed)
    return batch, students, quality


async def get_batch(session: AsyncSession, batch_id: str, tenant_id: str | None = None) -> UploadBatch | None:
    q = select(UploadBatch).where(UploadBatch.id == batch_id)
    if tenant_id:
        q = q.where(UploadBatch.tenant_id == tenant_id)
    result = await session.execute(q)
    return result.scalar_one_or_none()


async def get_students_by_batch(session: AsyncSession, batch_id: str, limit: int = 100) -> list[Student]:
    result = await session.execute(select(Student).where(Student.batch_id == batch_id).order_by(Student.nome).limit(limit))
    return list(result.scalars().all())
