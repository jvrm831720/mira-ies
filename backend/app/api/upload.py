from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Query, Form
from pydantic import BaseModel, Field
import pandas as pd
import io
import json
import re
from pathlib import Path
import uuid

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
)
from app.schemas.student import UploadBatchResponse
from app.models.student import Student
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


def read_file_to_dataframe(file_content: bytes, ext: str) -> pd.DataFrame:
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
                    return df.dropna(axis=1, how="all")
                except UnicodeDecodeError:
                    continue
            raise ValueError("Nao foi possivel decodificar o CSV")
        elif ext in ["xlsx", "xls"]:
            return pd.read_excel(io.BytesIO(file_content), dtype=str).dropna(axis=1, how="all")
        raise ValueError(f"Formato nao suportado: {ext}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Erro ao processar arquivo: {str(e)}")


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


@router.post("/upload/preview")
async def preview_students_file(
    file: UploadFile = File(...),
    column_mapping: str | None = Form(default=None),
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
    df = read_file_to_dataframe(content, ext)
    if df.empty:
        raise HTTPException(status_code=422, detail="Arquivo nao contem dados")
    try:
        prepared = prepare_import_rows(df, parse_column_mapping(column_mapping))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    result = {key: value for key, value in prepared.items() if not key.startswith("_")}
    matriculas = [item["data"]["matricula"] for item in prepared["_cleaned_rows"]]
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
    df = read_file_to_dataframe(content, ext)
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
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao persistir dados: {str(e)}")
    preview = [{"matricula": s.matricula, "nome": s.nome, "curso": s.curso, "semestre": s.semestre,
                "communication_opt_out": s.communication_opt_out,
                "dias_atraso_boleto": s.dias_atraso_boleto, "dias_sem_login": s.dias_sem_login,
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
