"""
Orquestração do scoring: features → modelo → SHAP → atualização no banco.
"""

from __future__ import annotations

from typing import Any
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.student import Student, UploadBatch
from app.ml.features import build_features_from_student, features_to_dataframe
from app.ml.model import (
    load_model, load_meta, predict_proba,
    probability_to_risk_score, risk_level_from_score, train_model,
)
from app.ml.explain import explain_instance, format_top_factors_human


def score_student_dict(student_data: dict) -> dict[str, Any]:
    model = load_model()
    features = build_features_from_student(student_data)
    X = features_to_dataframe([features])
    proba = float(predict_proba(model, X)[0])
    risk_score = probability_to_risk_score(proba)
    risk_level = risk_level_from_score(risk_score)
    top_factors = explain_instance(features, top_k=3)
    return {
        "risk_score": risk_score,
        "risk_level": risk_level,
        "probability": round(proba, 4),
        "shap_top_factors": top_factors,
        "shap_summary": format_top_factors_human(top_factors),
        "features_used": features,
    }


async def score_batch(session: AsyncSession, batch_id: str, force: bool = False) -> dict[str, Any]:
    result = await session.execute(select(UploadBatch).where(UploadBatch.id == batch_id))
    batch = result.scalar_one_or_none()
    if not batch:
        raise ValueError(f"Batch {batch_id} nao encontrado")

    query = select(Student).where(Student.batch_id == batch_id)
    if not force:
        query = query.where(Student.risk_score.is_(None))
    result = await session.execute(query)
    students = list(result.scalars().all())

    if not students:
        return {
            "batch_id": batch_id,
            "scored": 0,
            "message": "Nenhum aluno pendente de scoring",
            "summary": {"baixo": 0, "medio": 0, "critico": 0},
        }

    model = load_model()
    feature_dicts = [build_features_from_student(s) for s in students]
    X = features_to_dataframe(feature_dicts)
    probas = predict_proba(model, X)

    summary = {"baixo": 0, "medio": 0, "critico": 0}
    scored_details = []

    for i, student in enumerate(students):
        proba = float(probas[i])
        risk_score = probability_to_risk_score(proba)
        risk_level = risk_level_from_score(risk_score)
        top_factors = explain_instance(feature_dicts[i], top_k=3)
        student.risk_score = risk_score
        student.risk_level = risk_level
        student.shap_top_factors = {
            "top_3": top_factors,
            "summary": format_top_factors_human(top_factors),
            "probability": round(proba, 4),
        }
        student.updated_at = datetime.now(timezone.utc)
        summary[risk_level] = summary.get(risk_level, 0) + 1
        scored_details.append({
            "matricula": student.matricula,
            "nome": student.nome,
            "risk_score": risk_score,
            "risk_level": risk_level,
            "shap_summary": format_top_factors_human(top_factors),
        })

    batch.status = "scored"
    batch.processed_at = datetime.now(timezone.utc)
    await session.commit()

    return {
        "batch_id": batch_id,
        "scored": len(students),
        "summary": summary,
        "students": scored_details[:20],
        "message": f"{len(students)} alunos pontuados com sucesso",
    }


async def score_all_pending(session: AsyncSession) -> dict[str, Any]:
    result = await session.execute(
        select(Student.batch_id).where(Student.risk_score.is_(None)).distinct()
    )
    batch_ids = [row[0] for row in result.all()]
    totals = {"baixo": 0, "medio": 0, "critico": 0, "scored": 0}
    results = []
    for bid in batch_ids:
        res = await score_batch(session, bid)
        totals["scored"] += res["scored"]
        for k in ["baixo", "medio", "critico"]:
            totals[k] += res["summary"].get(k, 0)
        results.append(res)
    return {"batches_processed": len(batch_ids), "totals": totals, "details": results}


def get_model_info() -> dict[str, Any]:
    try:
        meta = load_meta()
        return {
            "status": "ready",
            "version": meta.get("version"),
            "auc": meta.get("auc"),
            "n_features": len(meta.get("feature_columns", [])),
            "features": meta.get("feature_labels_pt"),
            "trained_at": meta.get("trained_at"),
            "model_type": meta.get("model_type"),
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
