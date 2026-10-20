"""Pipeline unificado: records → DataFrame → persistencia (tenant_id obrigatorio) → score."""

from __future__ import annotations

from typing import Any
import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ingestion import create_batch_and_students
from app.services.connectors.base import CANONICAL_FIELDS


async def ingest_records(
    session: AsyncSession,
    *,
    records: list[dict[str, Any]],
    source: str,
    filename: str | None = None,
    auto_score: bool = True,
    tenant_id: str | None = None,
    tenant_slug: str | None = None,
) -> dict[str, Any]:
    if not records:
        raise ValueError("Nenhum registro valido para ingerir")
    if not tenant_id:
        raise ValueError("tenant_id e obrigatorio para ingestao multi-tenant")

    rows = [{k: r.get(k) for k in CANONICAL_FIELDS} for r in records]
    df = pd.DataFrame(rows)
    original_filename = filename or f"{source}_api_ingest.json"
    safe_filename = f"api_{source}_{original_filename}"

    batch, students, quality = await create_batch_and_students(
        session,
        filename=safe_filename,
        original_filename=original_filename,
        df=df,
        tenant_id=tenant_id,
    )

    if batch.columns is None:
        batch.columns = {}
    if isinstance(batch.columns, dict):
        batch.columns = {**batch.columns, "source": source, "ingest_mode": "api"}
    await session.commit()
    await session.refresh(batch)

    scoring_result = None
    if auto_score and students:
        try:
            from app.ml.scoring import score_batch
            scoring_result = await score_batch(
                session, batch.id, force=True, tenant_id=tenant_id, tenant_slug=tenant_slug
            )
        except Exception as e:
            scoring_result = {"error": str(e), "scored": 0}

    from app.schemas.student import UploadBatchResponse

    message = f"Ingestao via {source}: {len(students)} alunos persistidos"
    if scoring_result and scoring_result.get("scored"):
        message += f" | {scoring_result['scored']} pontuados"

    return {
        "message": message,
        "source": source,
        "batch": UploadBatchResponse.model_validate(batch),
        "students_imported": len(students),
        "records_received": len(records),
        "quality": quality,
        "scoring": scoring_result,
        "preview": [
            {
                "matricula": s.matricula,
                "nome": s.nome,
                "curso": s.curso,
                "dias_atraso_boleto": s.dias_atraso_boleto,
                "dias_sem_login": s.dias_sem_login,
                "risk_score": s.risk_score,
                "risk_level": s.risk_level,
            }
            for s in students[:5]
        ],
    }
