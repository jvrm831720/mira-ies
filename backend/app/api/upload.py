from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Query, Form, Header
from pydantic import BaseModel, Field
import pandas as pd
import io
import json
import re
from pathlib import Path
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import get_db
from app.core.auth import AuthContext, get_current_tenant, require_min_role
from app.services.ingestion import (
    COLUMN_LABELS,
    RECOMMENDED_COLUMNS,
    REQUIRED_COLUMNS,
    create_batch_and_students,
    get_batch,
    get_students_by_batch,
    prepare_import_rows,
    normalize_columns,
)
from app.schemas.student import UploadBatchResponse
from app.models.student import Student, UploadBatch
from app.models.consent import ConsentAuditEvent
from app.services.consent import apply_preference_changes, effective_preferences
from app.services.engagement import normalize_behavior_properties

router = APIRouter()
settings = get_settings()
UPLOAD_DIR = Path("data/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


class CommunicationPreferencePayload(BaseModel):
    opt_out: bool | None = None
    channels: dict[str, bool] | None = None
    topics: dict[str, bool] | None = None
    source_reference: str | None = Field(default=None, max_length=160)


class BehaviorPropertiesPayload(BaseModel):
    properties: dict[str, Any]


def sanitize_filename(filename: str) -> str:
    """Remove componentes de diretorio e caracteres perigosos (previne path traversal)."""
    # Treat both POSIX and Windows separators as path boundaries on every OS.
    normalized = (filename or "").replace(chr(92), "/")
    name = Path(normalized).name
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name).strip("._") or "upload"
    return name[-200:]


def validate_extension(filename: str) -> str:
    if not filename:
        raise HTTPException(status_code=400, detail="Nome do arquivo e obrigatorio")
    ext = filename.rsplit(".", 1)[-1].lower()
    if ext not in settings.allowed_extensions_list:
        raise HTTPException(status_code=400, detail=f"Extensao nao permitida. Use: {settings.allowed_extensions}")
    return ext


def read_file_to_dataframe(file_content: bytes, ext: str, sheet_name: str | None = None, expected_fields: set[str] | None = None) -> pd.DataFrame:
    """Le planilhas sempre como string (dtype=str): colunas de matricula/turma
    puramente numericas seriam inferidas como int pelo pandas, descartando
    zeros a esquerda (ex: "00123" -> 123) antes da validacao. Campos
    numericos sao convertidos explicitamente depois, em validate_and_clean_row.
    """
    try:
        if ext == "csv":
            for encoding in ["utf-8", "latin-1", "iso-8859-1", "cp1252"]:
                try:
                    df = pd.read_csv(io.BytesIO(file_content), encoding=encoding, dtype=str)
                    # Preserve explicitly supplied all-blank columns. They are evidence
                    # of a source refresh and must reach the data-quality gate.
                    return df
                except UnicodeDecodeError:
                    continue
            raise ValueError("Nao foi possivel decodificar o CSV")
        elif ext in ["xlsx", "xls"]:
            excel = pd.ExcelFile(io.BytesIO(file_content))
            selected_sheet = sheet_name
            if selected_sheet is None:
                # Multi-file and legacy clients do not send sheet_name. Prefer a unique
                # sheet whose headers identify both required student fields.
                required_candidates: list[str] = []
                tabular_candidates: list[str] = []
                for candidate in excel.sheet_names:
                    candidate_df = pd.read_excel(excel, sheet_name=candidate, dtype=str)
                    if candidate_df.empty or len(candidate_df.columns) < 2:
                        continue
                    tabular_candidates.append(candidate)
                    try:
                        _, candidate_mapping = normalize_columns(candidate_df)
                    except ValueError:
                        continue
                    mapped_fields = set(candidate_mapping.values())
                    if expected_fields is None:
                        matches = {"matricula", "nome"}.issubset(mapped_fields)
                    else:
                        role_fields_found = expected_fields.intersection(mapped_fields) - {"matricula"}
                        matches = "matricula" in mapped_fields and bool(role_fields_found)
                    if matches:
                        required_candidates.append(candidate)
                if len(required_candidates) == 1:
                    selected_sheet = required_candidates[0]
                elif len(required_candidates) > 1:
                    raise ValueError("Mais de uma aba parece conter cadastro de alunos. Selecione a aba explicitamente.")
                elif len(tabular_candidates) == 1:
                    selected_sheet = tabular_candidates[0]
                else:
                    selected_sheet = excel.sheet_names[0] if excel.sheet_names else 0
            return pd.read_excel(excel, sheet_name=selected_sheet if selected_sheet is not None else 0, dtype=str)
        raise ValueError(f"Formato nao suportado: {ext}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Erro ao processar arquivo: {str(e)}")



def inspect_file_structure(file_content: bytes, ext: str) -> dict[str, Any]:
    """Inspeciona abas, cabeçalhos e amostras sem validar nem persistir registros."""
    if ext == "csv":
        df = read_file_to_dataframe(file_content, ext)
        headers = [str(column) for column in df.columns]
        try:
            _, mapped = normalize_columns(df)
        except ValueError:
            mapped = {}
        required = {"matricula", "nome"}
        score = len(required.intersection(mapped.values()))
        return {
            "sheets": [{"name": "CSV", "rows": int(len(df)), "columns": headers,
                        "sample_rows": df.head(3).fillna("").astype(str).to_dict(orient="records"),
                        "recognized_fields": mapped, "required_fields_found": score == 2,
                        "tabular": not df.empty and len(headers) > 1}],
            "suggested_sheet": "CSV", "requires_sheet_selection": False,
        }

    try:
        excel = pd.ExcelFile(io.BytesIO(file_content))
        sheets = []
        for name in excel.sheet_names:
            try:
                df = pd.read_excel(excel, sheet_name=name, dtype=str).dropna(axis=1, how="all")
            except Exception:
                continue
            if df.empty and len(df.columns) == 0:
                continue
            headers = [str(column) for column in df.columns]
            try:
                _, mapped = normalize_columns(df)
            except ValueError:
                mapped = {}
            recognized = set(mapped.values())
            required_found = {"matricula", "nome"}.issubset(recognized)
            tabular = bool(headers) and len(headers) >= 2 and len(df) > 0
            sheets.append({
                "name": str(name),
                "rows": int(len(df)),
                "columns": headers,
                "sample_rows": df.head(3).fillna("").astype(str).to_dict(orient="records"),
                "recognized_fields": mapped,
                "required_fields_found": required_found,
                "tabular": tabular,
            })
        if not sheets:
            raise ValueError("Nenhuma aba contém uma tabela legível.")
        candidates = [sheet for sheet in sheets if sheet["required_fields_found"]]
        suggested = candidates[0]["name"] if len(candidates) == 1 else None
        if suggested is None:
            tabular_candidates = [sheet for sheet in sheets if sheet["tabular"]]
            if len(tabular_candidates) == 1:
                suggested = tabular_candidates[0]["name"]
        return {
            "sheets": sheets,
            "suggested_sheet": suggested,
            "requires_sheet_selection": suggested is None and len(sheets) > 1,
        }
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Não foi possível inspecionar as abas do arquivo: {exc}") from exc



# Contrato único de papéis usado tanto na prévia quanto na confirmação.
# Campos desconhecidos ou ausentes permanecem desconhecidos; o papel apenas
# limita quais colunas do arquivo podem alimentar o cadastro do estudante.
MULTI_UPLOAD_ROLE_FIELDS: dict[str, set[str]] = {
    "cadastro": {"matricula", "nome", "curso", "turma", "semestre", "forma_ingresso", "telefone", "email", "communication_opt_out"},
    "financeiro": {"matricula", "dias_atraso_boleto", "recorrencia_atrasos", "saldo_devedor", "status_financeiro"},
    "academico": {"matricula", "curso", "campus"},
    "historico": {"matricula", "dias_sem_login", "presenca_percentual", "nota_media", "reprovacoes"},
    "matriculas": {"matricula", "turma", "semestre", "forma_ingresso", "status_aluno"},
    # Aliases legados preservam os campos que cada papel podia importar antes
    # da unificação, sem ampliar silenciosamente o escopo de uma base.
    "alunos": {"matricula", "nome", "curso", "turma", "semestre", "forma_ingresso", "telefone", "email", "communication_opt_out"},
    "cursos": {"matricula", "nome", "curso", "turma", "semestre", "forma_ingresso", "telefone", "email", "communication_opt_out"},
    "engajamento": {"matricula", "dias_sem_login", "presenca_percentual"},
    "desempenho": {"matricula", "nota_media", "reprovacoes"},
}


def resolve_multi_upload_role(role: str | None) -> str | None:
    normalized = (role or "").strip().lower()
    return normalized if normalized in MULTI_UPLOAD_ROLE_FIELDS else None


def parse_column_mapping(value: str | None) -> dict[str, str] | None:
    if value is None or not value.strip():
        return None
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=422, detail="Mapeamento de colunas em formato inválido.") from exc
    if not isinstance(parsed, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in parsed.items()):
        raise HTTPException(status_code=422, detail="O mapeamento deve ser um objeto de cabeçalho para campo.")
    return parsed


@router.post("/upload/preview-multiple")
async def preview_multiple_students_files(
    files: list[UploadFile] = File(...),
    file_roles: list[str] = Form(default=[]),
    auth: AuthContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Pré-valida bases complementares por matrícula; nunca persiste dados."""
    if not files:
        raise HTTPException(status_code=422, detail="Selecione ao menos um arquivo.")
    if len(files) > 10:
        raise HTTPException(status_code=422, detail="O limite é de 10 arquivos por operação.")
    if file_roles and len(file_roles) != len(files):
        raise HTTPException(status_code=422, detail="Informe exatamente um tipo de base para cada arquivo.")

    role_fields = MULTI_UPLOAD_ROLE_FIELDS
    total_bytes = 0
    items: list[dict[str, Any]] = []
    all_matriculas: set[str] = set()
    consolidated: dict[str, dict[str, Any]] = {}
    seen_by_file: dict[str, set[str]] = {}
    conflicts: list[dict[str, Any]] = []
    duplicate_keys: list[dict[str, Any]] = []

    for index, upload in enumerate(files):
        ext = validate_extension(upload.filename)
        content = await upload.read()
        total_bytes += len(content)
        filename = sanitize_filename(upload.filename or "")
        submitted_role = file_roles[index] if index < len(file_roles) else "cadastro"
        role = resolve_multi_upload_role(submitted_role)
        if len(content) > settings.max_upload_size_mb * 1024 * 1024:
            raise HTTPException(status_code=413, detail=f"Arquivo {filename} excede o limite individual.")
        if not content:
            raise HTTPException(status_code=422, detail=f"Arquivo {filename} está vazio.")
        if role is None:
            items.append({"index": index, "filename": filename, "role": str(submitted_role).strip().lower(), "valid": False,
                          "error": "Tipo de base desconhecido. Use cadastro, financeiro, academico, historico ou matriculas.",
                          "total_rows": 0, "rows_to_import": 0, "rows_to_reject": 0,
                          "warnings": [], "errors": ["Tipo de base desconhecido."]})
            continue
        df = read_file_to_dataframe(content, ext, expected_fields=role_fields[role])
        if df.empty:
            raise HTTPException(status_code=422, detail=f"Arquivo {filename} não contém dados.")
        try:
            normalized, mapped = normalize_columns(df)
        except ValueError as exc:
            items.append({"index": index, "filename": filename, "role": str(submitted_role).strip().lower(), "valid": False,
                          "error": str(exc), "total_rows": int(len(df)), "rows_to_import": 0,
                          "rows_to_reject": int(len(df)), "warnings": [], "errors": [str(exc)]})
            continue

        allowed = role_fields[role]
        recognized = {field for field in mapped.values() if field in allowed}
        missing = {"matricula"} - recognized
        if role in {"cadastro", "alunos"}:
            missing |= {"nome"} - recognized
        if missing:
            required_labels = {"matricula": "matrícula", "nome": "nome"}
            missing_labels = ", ".join(required_labels.get(field, field) for field in sorted(missing))
            items.append({"index": index, "filename": filename, "role": str(submitted_role).strip().lower(), "valid": False,
                          "error": f"Colunas obrigatórias ausentes para {role}: {missing_labels}.",
                          "total_rows": int(len(df)), "rows_to_import": 0, "rows_to_reject": int(len(df)),
                          "columns": [{"key": str(k), "label": str(k)} for k in df.columns],
                          "mapped_columns": mapped, "warnings": [], "errors": [f"Colunas obrigatórias ausentes: {missing_labels}."]})
            continue

        # Mantém somente os campos permitidos para o papel escolhido.
        rows_by_key: dict[str, dict[str, Any]] = {}
        file_warnings: list[str] = []
        file_errors: list[str] = []
        for row_number, (_, row) in enumerate(normalized.iterrows(), start=2):
            key_value = str(row.get("matricula") or "").strip()
            if not key_value or key_value.lower() == "nan":
                file_errors.append(f"Linha {row_number}: matrícula ausente.")
                continue
            key_value = key_value[:50]
            record: dict[str, Any] = {}
            for field in allowed - {"matricula"}:
                if field not in normalized.columns:
                    continue
                value = row.get(field)
                if pd.isna(value) or str(value).strip() == "":
                    continue
                record[field] = str(value).strip()
            if key_value in rows_by_key:
                duplicate_keys.append({"filename": filename, "role": str(submitted_role).strip().lower(), "matricula": key_value})
                file_warnings.append(f"Matrícula duplicada {key_value}: a linha mais recente substitui a anterior nesta prévia.")
            rows_by_key[key_value] = record
            if key_value not in consolidated:
                consolidated[key_value] = {}
            for field, value in record.items():
                prior = consolidated[key_value].get(field)
                if prior is not None and str(prior) != str(value):
                    conflicts.append({"matricula": key_value, "field": field, "existing_value": prior,
                                      "incoming_value": value, "filename": filename,
                                      "message": "Valores diferentes para o mesmo campo; revisão manual necessária."})
                elif prior is None:
                    consolidated[key_value][field] = value
        all_matriculas.update(rows_by_key)
        seen_by_file[filename] = set(rows_by_key)
        existing: set[str] = set()
        if rows_by_key:
            query = select(Student.matricula).where(
                Student.tenant_id == auth.tenant_id,
                Student.matricula.in_(list(rows_by_key)),
            )
            existing = set((await db.execute(query)).scalars().all())
        items.append({
            "index": index, "filename": filename, "role": str(submitted_role).strip().lower(),
            "valid": not file_errors and bool(rows_by_key),
            "total_rows": int(len(df)), "rows_to_import": len(rows_by_key),
            "rows_to_reject": int(len(df)) - len(rows_by_key),
            "existing_matches": len(existing),
            "rows_that_will_be_created": max(0, len(rows_by_key) - len(existing)),
            "columns": [{"key": str(k), "label": str(k)} for k in df.columns],
            "mapped_columns": {k: v for k, v in mapped.items() if v in allowed},
            "warnings": file_warnings, "errors": file_errors,
        })

    if total_bytes > settings.max_upload_size_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail="O tamanho combinado dos arquivos excede o limite permitido.")
    valid_count = sum(1 for item in items if item["valid"])
    return {
        "items": items,
        "summary": {
            "files_received": len(files), "files_valid": valid_count,
            "files_with_errors": len(files) - valid_count,
            "distinct_matriculas_across_files": len(all_matriculas),
            "total_bytes": total_bytes, "consolidated_students": len(consolidated),
            "cross_file_conflicts": len(conflicts), "duplicate_matriculas": len(duplicate_keys),
        },
        "consolidated_preview": [
            {"matricula": key, "fields": value, "requires_review": any(c["matricula"] == key for c in conflicts)}
            for key, value in sorted(consolidated.items())
        ],
        "conflicts": conflicts,
        "duplicate_matriculas": duplicate_keys,
        "persisted": False,
        "cross_file_relationships_validated": True,
        "message": "Prévia consolidada por matrícula concluída. Nenhum dado foi salvo. Revise duplicidades e conflitos antes de habilitar a importação conjunta.",
    }


@router.post("/upload/structure")
async def inspect_students_file_structure(
    file: UploadFile = File(...),
    auth: AuthContext = Depends(get_current_tenant),
):
    """Detecta abas e mostra cabeçalhos/amostra antes de validar os registros."""
    ext = validate_extension(file.filename)
    content = await file.read()
    if not content:
        raise HTTPException(status_code=422, detail="Arquivo vazio.")
    if len(content) > settings.max_upload_size_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"Arquivo muito grande. Máximo: {settings.max_upload_size_mb} MB.")
    structure = inspect_file_structure(content, ext)
    return {"filename": sanitize_filename(file.filename or ""), "file_type": ext, **structure, "persisted": False}


@router.post("/upload/preview")
async def preview_students_file(
    file: UploadFile = File(...),
    column_mapping: str | None = Form(default=None),
    sheet_name: str | None = Form(default=None),
    auth: AuthContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Prévia autenticada e sem persistência; usa a mesma validação do upload."""
    ext = validate_extension(file.filename)
    content = await file.read()
    size_mb = len(content) / (1024 * 1024)
    if size_mb > settings.max_upload_size_mb:
        raise HTTPException(status_code=413, detail=f"Arquivo muito grande. Maximo: {settings.max_upload_size_mb}MB")
    if not content:
        raise HTTPException(status_code=422, detail="Arquivo vazio")
    df = read_file_to_dataframe(content, ext, sheet_name=sheet_name)
    if df.empty:
        raise HTTPException(status_code=422, detail="A aba selecionada não contém dados tabulares.")
    try:
        prepared = prepare_import_rows(df, parse_column_mapping(column_mapping))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    result = {key: value for key, value in prepared.items() if not key.startswith("_")}
    matriculas = [item["data"]["matricula"] for item in prepared["_cleaned_rows"] if item["data"]["matricula"] not in set(prepared.get("_conflicted_matriculas", []))]
    existing_matriculas: set[str] = set()
    if matriculas:
        query = select(Student.matricula).where(
            Student.tenant_id == auth.tenant_id,
            Student.matricula.in_(matriculas),
        )
        existing_matriculas = set((await db.execute(query)).scalars().all())

    result["existing_matches"] = len(existing_matriculas)
    result["rows_that_will_be_created"] = max(0, result["rows_to_import"] - len(existing_matriculas))
    result["field_labels"] = COLUMN_LABELS
    result["selected_sheet"] = sheet_name or ("CSV" if ext == "csv" else None)
    result["message"] = (
        "A prévia não salva dados. Matrículas já existentes nesta instituição serão atualizadas; "
        "células vazias não apagarão valores existentes."
    )
    return result


@router.post("/upload", status_code=201)
async def upload_students_file(
    file: UploadFile = File(...),
    auto_score: bool = Query(True),
    column_mapping: str | None = Form(default=None),
    sheet_name: str | None = Form(default=None),
    auth: AuthContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    ext = validate_extension(file.filename)
    content = await file.read()
    size_mb = len(content) / (1024 * 1024)
    if size_mb > settings.max_upload_size_mb:
        raise HTTPException(status_code=413, detail=f"Arquivo muito grande. Maximo: {settings.max_upload_size_mb}MB")
    if size_mb == 0:
        raise HTTPException(status_code=422, detail="Arquivo vazio")
    df = read_file_to_dataframe(content, ext, sheet_name=sheet_name)
    if df.empty:
        raise HTTPException(status_code=422, detail="Arquivo nao contem dados")
    batch_uuid = str(uuid.uuid4())
    safe_filename = f"{batch_uuid}_{sanitize_filename(file.filename)}"
    dest_path = (UPLOAD_DIR / safe_filename).resolve()
    if dest_path.parent != UPLOAD_DIR.resolve():
        raise HTTPException(status_code=400, detail="Nome de arquivo invalido")
    dest_path.write_bytes(content)
    mapping = parse_column_mapping(column_mapping)
    try:
        batch, students, quality = await create_batch_and_students(
            db, filename=safe_filename, original_filename=file.filename or "unknown",
            df=df, tenant_id=auth.tenant_id,
            column_mapping=mapping,
        )
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=422, detail=str(e))
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Erro ao persistir dados; nenhuma alteração foi confirmada.")
    preview = [{"matricula": s.matricula, "nome": s.nome, "curso": s.curso, "semestre": s.semestre,
                "communication_opt_out": s.communication_opt_out,
                "dias_atraso_boleto": s.dias_atraso_boleto, "saldo_devedor": s.saldo_devedor, "status_financeiro": s.status_financeiro, "dias_sem_login": s.dias_sem_login,
                "presenca_percentual": s.presenca_percentual, "nota_media": s.nota_media} for s in students[:5]]
    scoring_result = None
    if auto_score and students:
        try:
            from app.ml.scoring import score_batch
            scoring_result = await score_batch(
                db, batch.id, force=True, tenant_id=auth.tenant_id, tenant_slug=auth.tenant_slug
            )
        except Exception as e:
            scoring_result = {"error": str(e), "scored": 0}
    message = "Arquivo processado e dados persistidos com sucesso"
    if scoring_result and scoring_result.get("scored"):
        message += f" | {scoring_result['scored']} alunos pontuados"
    return {"message": message, "batch": UploadBatchResponse.model_validate(batch),
            "students_imported": len(students), "quality": quality, "preview": preview, "scoring": scoring_result}



@router.get("/upload/history")
async def list_upload_history(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    auth: AuthContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Lista somente os lotes da instituição autenticada, mais recentes primeiro."""
    result = await db.execute(
        select(UploadBatch)
        .where(UploadBatch.tenant_id == auth.tenant_id)
        .order_by(UploadBatch.uploaded_at.desc())
        .offset(offset)
        .limit(limit)
    )
    batches = result.scalars().all()
    return {
        "items": [
            {
                "id": batch.id,
                "filename": batch.original_filename,
                "status": batch.status,
                "total_rows": batch.total_rows,
                "processed_rows": batch.processed_rows,
                "uploaded_at": batch.uploaded_at,
                "processed_at": batch.processed_at,
                "error_message": batch.error_message,
            }
            for batch in batches
        ],
        "limit": limit,
        "offset": offset,
        "has_more": len(batches) == limit,
    }


@router.get("/upload/status/{batch_id}")
async def get_upload_status(batch_id: str, auth: AuthContext = Depends(get_current_tenant), db: AsyncSession = Depends(get_db)):
    batch = await get_batch(db, batch_id, tenant_id=auth.tenant_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch nao encontrado")
    students = await get_students_by_batch(db, batch_id, limit=15)
    return {"batch": UploadBatchResponse.model_validate(batch),
            "students_sample": [{"matricula": s.matricula, "nome": s.nome, "curso": s.curso,
                "risk_score": s.risk_score, "risk_level": s.risk_level,
                "shap_summary": (s.shap_top_factors or {}).get("summary")} for s in students],
            "total_students": batch.processed_rows}


@router.get("/students")
async def list_students(
    batch_id: str | None = None, risk_level: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    auth: AuthContext = Depends(get_current_tenant), db: AsyncSession = Depends(get_db),
):
    query = select(Student).where(Student.tenant_id == auth.tenant_id).order_by(Student.nome).limit(limit)
    if batch_id:
        query = query.where(Student.batch_id == batch_id)
    if risk_level:
        query = query.where(Student.risk_level == risk_level.lower())
    result = await db.execute(query)
    students = result.scalars().all()
    return {"count": len(students), "students": [{
        "id": s.id, "matricula": s.matricula, "nome": s.nome, "curso": s.curso, "turma": s.turma,
        "semestre": s.semestre, "dias_atraso_boleto": s.dias_atraso_boleto, "dias_sem_login": s.dias_sem_login,
        "communication_opt_out": s.communication_opt_out,
        "presenca_percentual": s.presenca_percentual, "nota_media": s.nota_media,
        "risk_score": s.risk_score, "risk_level": s.risk_level,
        "shap_summary": (s.shap_top_factors or {}).get("summary"),
        "shap_top_factors": s.shap_top_factors,
    } for s in students]}


def _preference_response(student: Student) -> dict:
    preferences = effective_preferences(student)
    return {
        "student_id": student.id,
        "opt_out": bool(student.communication_opt_out),
        "communication_opt_out": bool(student.communication_opt_out),
        "communication_opted_out_at": student.communication_opted_out_at,
        "channels": preferences["channels"],
        "topics": preferences["topics"],
    }


@router.get("/students/{student_id}/communication-preferences")
async def get_communication_preferences(
    student_id: str,
    auth: AuthContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Student).where(Student.id == student_id, Student.tenant_id == auth.tenant_id)
    )
    student = result.scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="Aluno não encontrado")
    return _preference_response(student)


@router.patch("/students/{student_id}/communication-preferences")
async def update_communication_preferences(
    student_id: str,
    body: CommunicationPreferencePayload,
    auth: AuthContext = Depends(require_min_role("operator")),
    db: AsyncSession = Depends(get_db),
):
    if body.opt_out is None and not body.channels and not body.topics:
        raise HTTPException(status_code=422, detail="Informe ao menos uma preferência para alterar.")
    result = await db.execute(
        select(Student).where(Student.id == student_id, Student.tenant_id == auth.tenant_id)
    )
    student = result.scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="Aluno não encontrado")
    try:
        events_created = apply_preference_changes(
            db,
            tenant_id=auth.tenant_id,
            student=student,
            opt_out=body.opt_out,
            channels=body.channels,
            topics=body.topics,
            source="authenticated_api",
            method="manual_preferences_update",
            location="student_profile_preferences",
            source_reference=body.source_reference,
            actor_user_id=auth.user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await db.commit()
    await db.refresh(student)
    response = _preference_response(student)
    response["audit_events_created"] = events_created
    return response


@router.get("/students/{student_id}/consent-audit")
async def list_consent_audit(
    student_id: str,
    limit: int = Query(50, ge=1, le=100),
    auth: AuthContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    student_result = await db.execute(
        select(Student.id).where(Student.id == student_id, Student.tenant_id == auth.tenant_id)
    )
    if student_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Aluno não encontrado")
    result = await db.execute(
        select(ConsentAuditEvent)
        .where(
            ConsentAuditEvent.tenant_id == auth.tenant_id,
            ConsentAuditEvent.student_id == student_id,
        )
        .order_by(ConsentAuditEvent.occurred_at.desc())
        .limit(limit)
    )
    events = result.scalars().all()
    return {
        "count": len(events),
        "events": [
            {
                "id": event.id,
                "event_type": event.event_type,
                "channel": event.channel,
                "topic": event.topic,
                "previous_value": event.previous_value,
                "new_value": event.new_value,
                "source": event.source,
                "method": event.method,
                "location": event.location,
                "source_reference": event.source_reference,
                "actor_user_id": event.actor_user_id,
                "occurred_at": event.occurred_at,
                "notes": event.notes,
            }
            for event in events
        ],
    }


@router.get("/students/{student_id}/behavior-properties")
async def get_student_behavior_properties(
    student_id: str,
    auth: AuthContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Student).where(Student.id == student_id, Student.tenant_id == auth.tenant_id)
    )
    student = result.scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="Aluno não encontrado")
    return {
        "student_id": student.id,
        "properties": student.behavior_properties or {},
        "engagement_score": student.engagement_score,
        "engagement_score_updated_at": student.engagement_score_updated_at,
        "model_risk_score": student.model_risk_score,
        "risk_score": student.risk_score,
        "risk_level": student.risk_level,
        "dynamic_risk_adjustment": student.dynamic_risk_adjustment,
    }


@router.patch("/students/{student_id}/behavior-properties")
async def update_student_behavior_properties(
    student_id: str,
    body: BehaviorPropertiesPayload,
    auth: AuthContext = Depends(require_min_role("operator")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Student).where(Student.id == student_id, Student.tenant_id == auth.tenant_id)
    )
    student = result.scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="Aluno não encontrado")
    if not body.properties:
        raise HTTPException(status_code=422, detail="Informe ao menos uma propriedade comportamental.")
    try:
        student.behavior_properties = normalize_behavior_properties(
            student.behavior_properties or {}, body.properties
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await db.commit()
    await db.refresh(student)
    return {
        "student_id": student.id,
        "properties": student.behavior_properties,
        "message_fields": student.behavior_properties.get("message_fields", []),
    }


@router.get("/upload/expected-columns")
async def expected_columns():
    from app.services.ingestion import COLUMN_ALIASES
    return {
        "required": sorted(REQUIRED_COLUMNS),
        "recommended_for_risk_model": sorted(RECOMMENDED_COLUMNS),
        "field_labels": COLUMN_LABELS,
        "all_supported_aliases": {key: values for key, values in COLUMN_ALIASES.items()},
        "tip": "A planilha precisa ter pelo menos matrícula e nome. O mapeamento é determinístico por aliases e pode ser ajustado manualmente.",
    }


@router.post("/upload/confirm-multiple", status_code=201)
async def confirm_multiple_students_files(
    files: list[UploadFile] = File(...),
    file_roles: list[str] = Form(default=[]),
    auth: AuthContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
):
    """Valida e persiste bases complementares em um único lote transacional."""
    if not idempotency_key.strip() or len(idempotency_key) > 200:
        raise HTTPException(status_code=400, detail="Idempotency-Key é obrigatória e deve ter até 200 caracteres.")
    deterministic_batch_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"mira-import:{auth.tenant_id}:{idempotency_key.strip()}"))
    prior_batch = await db.execute(
        select(UploadBatch).where(
            UploadBatch.id == deterministic_batch_id,
            UploadBatch.tenant_id == auth.tenant_id,
        )
    )
    existing_batch = prior_batch.scalar_one_or_none()
    if existing_batch is not None:
        existing_students = await db.execute(
            select(Student.id).where(Student.tenant_id == auth.tenant_id, Student.batch_id == existing_batch.id)
        )
        return {
            "message": "Esta confirmação já foi processada; resultado anterior reutilizado.",
            "batch": UploadBatchResponse.model_validate(existing_batch),
            "students_imported": len(existing_students.scalars().all()),
            "persisted": True,
            "idempotent_replay": True,
        }
    if not files:
        raise HTTPException(status_code=422, detail="Selecione ao menos um arquivo.")
    if len(files) > 10:
        raise HTTPException(status_code=422, detail="O limite é de 10 arquivos por operação.")
    if len(file_roles) != len(files):
        raise HTTPException(status_code=422, detail="Informe exatamente um tipo de base para cada arquivo.")

    role_fields = MULTI_UPLOAD_ROLE_FIELDS
    total_bytes = 0
    consolidated: dict[str, dict[str, Any]] = {}
    sources: list[str] = []
    duplicates: list[dict[str, str]] = []
    conflicts: list[dict[str, str]] = []
    errors: list[str] = []
    allowed_all = set().union(*role_fields.values()) - {"matricula"}

    for index, upload in enumerate(files):
        ext = validate_extension(upload.filename)
        raw_content = await upload.read()
        total_bytes += len(raw_content)
        filename = sanitize_filename(upload.filename or "")
        if not raw_content:
            errors.append(f"{filename}: arquivo vazio.")
            continue
        if len(raw_content) > settings.max_upload_size_mb * 1024 * 1024:
            raise HTTPException(status_code=413, detail=f"Arquivo {filename} excede o limite individual.")
        submitted_role = file_roles[index]
        role = resolve_multi_upload_role(submitted_role)
        if role is None:
            errors.append(f"{filename}: tipo de base desconhecido ({str(submitted_role).strip().lower()}).")
            continue
        try:
            df = read_file_to_dataframe(raw_content, ext, expected_fields=role_fields[role])
            normalized, mapped = normalize_columns(df)
        except (HTTPException, ValueError) as exc:
            errors.append(f"{filename}: {str(exc)}")
            continue
        if df.empty:
            errors.append(f"{filename}: arquivo sem dados.")
            continue
        allowed = role_fields[role]
        recognized = {field for field in mapped.values() if field in allowed}
        missing = {"matricula"} - recognized
        if role == "cadastro":
            missing |= {"nome"} - recognized
        if missing:
            errors.append(f"{filename}: colunas obrigatórias ausentes: {', '.join(sorted(missing))}.")
            continue

        file_seen: set[str] = set()
        sources.append(filename)
        for row_number, (_, row) in enumerate(normalized.iterrows(), start=2):
            key = str(row.get("matricula") or "").strip()
            if not key or key.lower() == "nan":
                errors.append(f"{filename}, linha {row_number}: matrícula ausente.")
                continue
            key = key[:50]
            if key in file_seen:
                duplicates.append({"filename": filename, "matricula": key})
                continue
            file_seen.add(key)
            target = consolidated.setdefault(key, {})
            for field in allowed_all.intersection(allowed):
                if field not in normalized.columns:
                    continue
                value = row.get(field)
                if pd.isna(value) or str(value).strip() == "":
                    continue
                value = str(value).strip()
                prior = target.get(field)
                if prior is not None and prior != value:
                    conflicts.append({"filename": filename, "matricula": key, "field": field})
                else:
                    target[field] = value

    if total_bytes > settings.max_upload_size_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail="O tamanho combinado dos arquivos excede o limite permitido.")
    if errors or duplicates or conflicts:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Importação bloqueada. Corrija os erros, duplicidades e conflitos antes de confirmar.",
                "errors": errors[:50],
                "duplicates": duplicates[:50],
                "conflicts": conflicts[:50],
            },
        )
    if not consolidated:
        raise HTTPException(status_code=422, detail="Nenhum registro válido foi encontrado.")

    existing_result = await db.execute(
        select(Student).where(
            Student.tenant_id == auth.tenant_id,
            Student.matricula.in_(list(consolidated.keys())),
        )
    )
    existing_by_key = {student.matricula: student for student in existing_result.scalars().all()}
    rows: list[dict[str, Any]] = []
    for matricula, fields in consolidated.items():
        name = fields.get("nome")
        existing = existing_by_key.get(matricula)
        if not name and existing is not None:
            name = existing.nome
        if not name:
            errors.append(f"Matrícula {matricula}: não há nome para criar um novo aluno.")
            continue
        row = {"matricula": matricula, "nome": name}
        for field, value in fields.items():
            if field == "matricula":
                continue
            row[field] = value
        rows.append(row)
    if errors:
        raise HTTPException(status_code=422, detail={"message": "Não foi possível confirmar a importação.", "errors": errors[:50]})

    df_consolidated = pd.DataFrame(rows)
    batch_id = str(uuid.uuid4())
    safe_filename = f"{batch_id}_importacao_multipla.csv"
    try:
        batch, students, quality = await create_batch_and_students(
            db,
            batch_id=deterministic_batch_id,
            filename=safe_filename,
            original_filename="Importação de bases complementares: " + ", ".join(sources)[:220],
            df=df_consolidated,
            tenant_id=auth.tenant_id,
        )
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Falha ao persistir a importação; nenhuma alteração foi confirmada.") from exc

    return {
        "message": "Bases complementares importadas com sucesso.",
        "batch": UploadBatchResponse.model_validate(batch),
        "students_imported": len(students),
        "quality": quality,
        "sources": sources,
        "persisted": True,
        "idempotent_replay": False,
    }
