"""Orquestracao do scoring: features → modelo → regras → SHAP → TrainingEvent → banco."""

from __future__ import annotations

from typing import Any
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.student import Student, UploadBatch
from app.models.tenant import TrainingEvent
from app.services.tenant import get_or_create_tenant, ensure_base_model_registered
from app.ml.features import (
    build_features_from_student,
    features_to_dataframe,
    missing_feature_flags,
)
from app.ml.model import load_model, load_meta, predict_proba, probability_to_risk_score
from app.ml.explain import explain_instance, format_top_factors_human
from app.ml.rules import apply_business_rules


def score_student_dict(student_data: dict) -> dict[str, Any]:
    model = load_model()
    features = build_features_from_student(student_data)
    X = features_to_dataframe([features])
    proba = float(predict_proba(model, X)[0])
    model_score = probability_to_risk_score(proba)
    rules = apply_business_rules(features, model_score)
    top_factors = explain_instance(features, top_k=3)
    missing = missing_feature_flags(student_data)
    return {
        "risk_score": rules["adjusted_score"],
        "model_score": rules["model_score"],
        "risk_level": rules["risk_level"],
        "probability": round(proba, 4),
        "shap_top_factors": top_factors,
        "shap_summary": format_top_factors_human(top_factors),
        "features_used": features,
        "rule_flags": rules["rule_flags"],
        "rule_boost": rules["rule_boost"],
        "recommended_actions": rules["recommended_actions"],
        "confidence": rules["confidence"],
        "missing_features": missing,
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

    tenant = await get_or_create_tenant(session, slug="default")
    tenant_id = tenant.id
    await ensure_base_model_registered(session)
    try:
        model_version = str(load_meta().get("version", "0.3.1"))
    except Exception:
        model_version = "0.3.1"

    if not batch.tenant_id:
        batch.tenant_id = tenant_id
    for s in students:
        if not s.tenant_id:
            s.tenant_id = tenant_id

    summary = {"baixo": 0, "medio": 0, "critico": 0}
    scored_details = []

    for i, student in enumerate(students):
        proba = float(probas[i])
        model_score = probability_to_risk_score(proba)
        rules = apply_business_rules(feature_dicts[i], model_score)
        top_factors = explain_instance(feature_dicts[i], top_k=3)
        student.risk_score = rules["adjusted_score"]
        student.risk_level = rules["risk_level"]
        student.shap_top_factors = {
            "top_3": top_factors,
            "summary": format_top_factors_human(top_factors),
            "probability": round(proba, 4),
            "model_score": rules["model_score"],
            "rule_flags": rules["rule_flags"],
            "rule_boost": rules["rule_boost"],
            "recommended_actions": rules["recommended_actions"],
            "confidence": rules["confidence"],
        }
        student.updated_at = datetime.now(timezone.utc)

        if tenant_id:
            session.add(TrainingEvent(
                tenant_id=tenant_id,
                student_id=student.id,
                batch_id=batch_id,
                matricula=student.matricula,
                features_snapshot=feature_dicts[i],
                model_score=rules["model_score"],
                adjusted_score=rules["adjusted_score"],
                risk_level=rules["risk_level"],
                model_version=model_version,
                model_scope="base",
            ))

        summary[rules["risk_level"]] = summary.get(rules["risk_level"], 0) + 1
        scored_details.append({
            "matricula": student.matricula,
            "nome": student.nome,
            "risk_score": rules["adjusted_score"],
            "risk_level": rules["risk_level"],
            "confidence": rules["confidence"],
            "shap_summary": format_top_factors_human(top_factors),
            "recommended_actions": rules["recommended_actions"][:2],
        })

    batch.status = "scored"
    batch.processed_at = datetime.now(timezone.utc)
    await session.commit()

    return {
        "batch_id": batch_id,
        "scored": len(students),
        "summary": summary,
        "students": scored_details[:20],
        "message": f"{len(students)} alunos pontuados (modelo + regras + snapshot learning)",
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
            "average_precision": meta.get("average_precision"),
            "brier_score": meta.get("brier_score"),
            "n_features": meta.get("n_features"),
            "features": meta.get("feature_labels_pt"),
            "top_features": meta.get("feature_importance", [])[:5],
            "classification_report": meta.get("classification_report"),
            "trained_at": meta.get("trained_at"),
            "model_type": meta.get("model_type"),
            "hybrid": "XGBoost calibrado + regras + learning loop (Modelo C)",
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
