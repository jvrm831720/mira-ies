"""API de importação inteligente: preview (dry-run) + apply (upsert idempotente)."""

import json
import hashlib
import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, UploadFile
from pydantic import BaseModel

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.upload import read_file_to_dataframe, sanitize_filename, validate_extension
from app.core.auth import AuthContext, require_permission
from app.core.config import get_settings
from app.db.session import get_db
from app.models.student import Student
from app.services import custom_fields as cf_service
from app.services import smart_import as engine

router = APIRouter()
settings = get_settings()


def _canonical_aliases() -> dict[str, list[str]]:
    try:
        from app.services.ingestion import COLUMN_ALIASES
        return {k: list(v) for k, v in COLUMN_ALIASES.items()}
    except Exception:
        return {}


async def _load_catalog(db: AsyncSession, tenant_id: str):
    definitions = await cf_service.list_definitions(db, tenant_id, target="student")
    return engine.build_catalog_by_field(
        cf_service.build_catalog(definitions), canonical_aliases=_canonical_aliases()
    )


def _catalog_index(catalog: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {entry["field"]: entry for entry in catalog}


def _validate_mapping(mapping: dict[str, str], headers: list[str], catalog: list[dict[str, Any]]) -> None:
    fields = _catalog_index(catalog)
    unknown_headers = sorted(set(mapping) - set(headers))
    unknown_fields = sorted(set(mapping.values()) - set(fields))
    if unknown_headers or unknown_fields:
        raise HTTPException(status_code=422, detail={
            "message": "Mapeamento contém colunas ou campos desconhecidos.",
            "headers": unknown_headers, "fields": unknown_fields,
        })
    if len(set(mapping.values())) != len(mapping):
        raise HTTPException(status_code=422, detail="Um campo da MIRA não pode receber duas colunas.")
    if list(mapping.values()).count(engine.DEFAULT_KEY_FIELD) != 1:
        raise HTTPException(status_code=422, detail="Mapeie exatamente uma coluna para matrícula.")


class ApplyMapping(BaseModel):
    mapping: dict[str, str]  # header -> campo (canônico ou custom)
    key_field: str = engine.DEFAULT_KEY_FIELD


@router.post("/import/preview")
async def preview_import(
    file: UploadFile = File(...),
    mapping_payload: str | None = Form(default=None),
    auth: AuthContext = Depends(require_permission("data.import", allow_service_key=True)),
    db: AsyncSession = Depends(get_db),
):
    """Dry-run completo: mapeamento sugerido, validação linha a linha, zero escrita."""
    ext = validate_extension(file.filename)
    content = await file.read()
    if not content:
        raise HTTPException(status_code=422, detail="Arquivo vazio.")
    if len(content) > settings.max_upload_size_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Arquivo excede o limite permitido.")
    df = read_file_to_dataframe(content, ext)
    if df.empty:
        raise HTTPException(status_code=422, detail="O arquivo não contém dados.")

    headers = [str(column) for column in df.columns]
    catalog = await _load_catalog(db, auth.tenant_id)
    mapping, suggestions, unmapped = engine.suggest_mapping(headers, catalog)
    if mapping_payload is not None:
        try:
            selected = ApplyMapping.model_validate(json.loads(mapping_payload))
            requested = {h: field for h, field in selected.mapping.items() if field}
        except (ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=422, detail=f"Mapeamento inválido: {exc}") from exc
        _validate_mapping(requested, headers, catalog)
        index = _catalog_index(catalog)
        mapping = {h: {**index[field], "field": field, "confidence": 1.0} for h, field in requested.items()}
        suggestions = {}
        unmapped = [h for h in headers if h not in mapping]

    key_field = engine.DEFAULT_KEY_FIELD
    key_header = next((h for h, m in mapping.items() if m["field"] == key_field), None)
    row_errors: list[dict[str, Any]] = []
    key_stats: dict[str, Any] = {"valid": 0, "invalid": 0, "duplicates": 0, "existing": 0}
    if key_header is not None:
        try:
            validated = engine.validate_records(df, mapping, _catalog_index(catalog), key_field)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        row_errors = validated["row_errors"]
        key_stats = validated["key_stats"]
        keys = [r["key"] for r in validated["records"]]
        existing_keys: set[str] = set()
        if keys:
            existing = await db.execute(
                select(Student.matricula).where(
                    Student.tenant_id == auth.tenant_id, Student.matricula.in_(keys)
                )
            )
            existing_keys = set(existing.scalars().all())
        key_stats["existing"] = len(existing_keys)
        missing_names = [
            r for r in validated["records"]
            if r["key"] not in existing_keys and not r["standard"].get("nome")
        ]
        key_stats["missing_name"] = len(missing_names)
        key_stats["valid"] -= len(missing_names)
        key_stats["invalid"] += len(missing_names)
        for r in missing_names[:max(0, engine.MAX_ROW_ERRORS_RETURNED - len(row_errors))]:
            row_errors.append({"row": r["row"], "field": "nome",
                               "message": "Aluno novo sem nome; inclua a coluna nome."})

    return {
        "filename": sanitize_filename(file.filename or ""),
        "headers": headers,
        "fields": catalog,
        "total_rows": int(len(df)),
        "key_field": key_field,
        "key_header": key_header,
        "mapping": mapping,
        "suggestions": suggestions,
        "unmapped_columns": unmapped,
        "row_errors": row_errors,
        "key_stats": {**key_stats,
                      "new": max(0, key_stats["valid"] - key_stats["existing"])},
        "sample_rows": df.head(5).fillna("").astype(str).to_dict(orient="records"),
    }


@router.post("/import/apply", status_code=201)
async def apply_import(
    file: UploadFile = File(...),
    payload: str = Form(...),  # JSON string do ApplyMapping
    auto_score: bool = Query(True),
    auth: AuthContext = Depends(require_permission("data.import", allow_service_key=True)),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
):
    """Persiste a importação (upsert). Repetir a mesma Idempotency-Key devolve
    o resultado anterior sem duplicar nada."""
    if not idempotency_key.strip() or len(idempotency_key) > 200:
        raise HTTPException(status_code=400, detail="Idempotency-Key é obrigatória (até 200 caracteres).")
    try:
        body = ApplyMapping.model_validate(json.loads(payload))
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=422, detail=f"Mapeamento inválido: {exc}") from exc

    if body.key_field != engine.DEFAULT_KEY_FIELD:
        raise HTTPException(status_code=422, detail="Apenas matrícula pode ser usada como chave.")

    deterministic_batch_id = str(uuid.uuid5(
        uuid.NAMESPACE_URL, f"mira-smart-import:{auth.tenant_id}:{idempotency_key.strip()}"
    ))
    from app.models.student import UploadBatch
    prior = await db.execute(
        select(UploadBatch).where(
            UploadBatch.id == deterministic_batch_id, UploadBatch.tenant_id == auth.tenant_id
        )
    )
    prior_batch = prior.scalar_one_or_none()

    ext = validate_extension(file.filename)
    content = await file.read()
    if not content:
        raise HTTPException(status_code=422, detail="Arquivo vazio.")
    if len(content) > settings.max_upload_size_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Arquivo excede o limite permitido.")
    fingerprint = hashlib.sha256(content + json.dumps({**body.model_dump(), "auto_score": auto_score}, sort_keys=True).encode()).hexdigest()
    if prior_batch is not None:
        metadata = prior_batch.columns or {}
        if metadata.get("fingerprint") != fingerprint:
            raise HTTPException(status_code=409, detail="Idempotency-Key reutilizada com conteúdo diferente.")
        return {"batch_id": deterministic_batch_id, "idempotent_replay": True,
                **(metadata.get("result_summary") or {})}
    df = read_file_to_dataframe(content, ext)
    if df.empty:
        raise HTTPException(status_code=422, detail="O arquivo não contém dados.")

    catalog = await _load_catalog(db, auth.tenant_id)
    catalog_index = _catalog_index(catalog)
    requested = {h: field for h, field in body.mapping.items() if field}
    _validate_mapping(requested, [str(col) for col in df.columns], catalog)
    mapping = {
        header: {**catalog_index[field], "field": field}
        for header, field in requested.items()
    }
    try:
        validated = engine.validate_records(df, mapping, catalog_index, body.key_field)
        if not validated["records"]:
            raise ValueError("Nenhuma linha válida para importar.")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    filename = sanitize_filename(file.filename or "")
    try:
        result = await engine.apply_smart_import(
            db, tenant_id=auth.tenant_id, batch_id=deterministic_batch_id,
            filename=f"{deterministic_batch_id}_{filename}", original_filename=filename,
            validated=validated, mapping=mapping, key_field=body.key_field,
            fingerprint=fingerprint,
        )
    except IntegrityError as exc:
        await db.rollback()
        # O rollback encerra a transação e limpa o contexto RLS; restaure o tenant autenticado.
        await db.execute(
            text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
            {"tenant_id": auth.tenant_id},
        )
        current = await db.execute(
            select(UploadBatch).where(
                UploadBatch.id == deterministic_batch_id,
                UploadBatch.tenant_id == auth.tenant_id,
            )
        )
        winner = current.scalar_one_or_none()
        if winner is not None and (winner.columns or {}).get("fingerprint") == fingerprint:
            return {"batch_id": deterministic_batch_id, "idempotent_replay": True,
                    **((winner.columns or {}).get("result_summary") or {})}
        raise HTTPException(
            status_code=409, detail="Importação concorrente ou conflito de chave; tente novamente."
        ) from exc
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # Mesmo contrato do upload legado: scoring após commit; falta de dados
    # produz status indeterminado, jamais risco favorável artificial.
    scoring_result: dict[str, Any] | None = None
    if auto_score and result["created"] + result["updated"] > 0:
        try:
            from app.ml.scoring import score_batch
            scored = await score_batch(
                db, deterministic_batch_id, force=True,
                tenant_id=auth.tenant_id, tenant_slug=auth.tenant_slug,
            )
            # A permissão de importação não concede acesso a scores individuais.
            scoring_result = {
                "scored": scored.get("scored", 0),
                "indeterminate_count": scored.get("indeterminate_count", 0),
            }
        except Exception:
            await db.rollback()
            scoring_result = {
                "scored": 0,
                "error": "A importação foi gravada, mas a pontuação não foi concluída.",
            }
        # Armazena somente um resumo para o replay idempotente.
        scoring_summary = {
            "scored": scoring_result.get("scored", 0),
            "indeterminate_count": scoring_result.get("indeterminate_count", 0),
        }
        if scoring_result.get("error"):
            scoring_summary["error"] = scoring_result["error"]
        try:
            await db.execute(
                text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
                {"tenant_id": auth.tenant_id},
            )
            batch = await db.get(UploadBatch, deterministic_batch_id)
            if batch is not None and batch.tenant_id == auth.tenant_id:
                prior_metadata = batch.columns or {}
                batch.columns = {
                    **prior_metadata,
                    "result_summary": {
                        **(prior_metadata.get("result_summary") or {}),
                        "scoring": scoring_summary,
                    },
                }
                await db.commit()
        except Exception:
            await db.rollback()

    return {
        "batch_id": deterministic_batch_id,
        "idempotent_replay": False,
        "scoring": scoring_result,
        "created": result["created"],
        "updated": result["updated"],
        "rejected": result["rejected"],
        "rejected_rows": result["rejected_rows"],
        "row_errors": result["row_errors"],
    }
