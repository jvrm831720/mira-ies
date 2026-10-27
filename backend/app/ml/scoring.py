"""Orquestracao do scoring — isolado por tenant_id, SHAP sob demanda."""

from __future__ import annotations

from typing import Any
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import text

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.student import Student, UploadBatch
from app.models.risk_assessment import RiskAssessment
from app.models.tenant import TrainingEvent, Tenant
from app.services.tenant import ensure_base_model_registered
from app.ml.features import build_features_from_student, features_to_dataframe, missing_feature_flags
from app.ml.model import load_model, load_meta, predict_proba, probability_to_risk_score
from app.ml.explain import explain_instance, format_top_factors_human
from app.ml.rules import apply_business_rules
from app.ml.tenant_train import resolve_scoring_model, predict_proba_with_model


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
        "risk_score": rules["adjusted_score"], "model_score": rules["model_score"],
        "risk_level": rules["risk_level"], "probability": round(proba, 4),
        "shap_top_factors": top_factors, "shap_summary": format_top_factors_human(top_factors),
        "features_used": features, "rule_flags": rules["rule_flags"], "rule_boost": rules["rule_boost"],
        "recommended_actions": rules["recommended_actions"], "confidence": rules["confidence"],
        "missing_features": missing,
    }


async def score_batch(
    session: AsyncSession,
    batch_id: str,
    force: bool = False,
    *,
    tenant_id: str,
    tenant_slug: str | None = None,
    explain: bool | None = None,
) -> dict[str, Any]:
    """Pontua batch isolado por tenant. SHAP default off (SHAP_ON_BATCH=false)."""
    from app.core.config import get_settings
    settings = get_settings()
    if explain is None:
        explain = settings.shap_on_batch
    await session.execute(text("SELECT set_config('app.tenant_id', :tenant_id, true)"), {"tenant_id": tenant_id})

    result = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise ValueError("Tenant nao encontrado")
    if tenant_slug and tenant.slug != tenant_slug:
        raise ValueError("tenant_slug nao corresponde ao tenant_id")

    result = await session.execute(
        select(UploadBatch).where(UploadBatch.id == batch_id, UploadBatch.tenant_id == tenant_id)
    )
    batch = result.scalar_one_or_none()
    if not batch:
        raise ValueError(f"Batch {batch_id} nao encontrado")

    query = select(Student).where(Student.batch_id == batch_id, Student.tenant_id == tenant_id)
    if not force:
        query = query.where(Student.risk_score.is_(None))
    students = list((await session.execute(query)).scalars().all())
    if not students:
        return {"batch_id": batch_id, "scored": 0, "message": "Nenhum aluno pendente", "summary": {"baixo": 0, "medio": 0, "critico": 0}}

    await ensure_base_model_registered(session)
    model, calibrator, model_scope, model_version = await resolve_scoring_model(session, tenant)
    feature_dicts = [build_features_from_student(s) for s in students]
    X = features_to_dataframe(feature_dicts)
    probas = predict_proba_with_model(model, X, calibrator)

    summary = {"baixo": 0, "medio": 0, "critico": 0}
    scored_details = []
    scoring_run_id = str(uuid4())
    evaluated_at = datetime.now(timezone.utc)
    for i, student in enumerate(students):
        proba = float(probas[i])
        model_score = probability_to_risk_score(proba)
        rules = apply_business_rules(feature_dicts[i], model_score)
        top_factors = explain_instance(feature_dicts[i], top_k=3) if explain else []
        student.model_risk_score = rules["adjusted_score"]
        dynamic_adjustment = float(student.dynamic_risk_adjustment or 0.0)
        final_score = round(min(100.0, rules["adjusted_score"] + dynamic_adjustment), 1)
        final_level = (
            "critico" if final_score >= 70
            else "medio" if final_score >= 40
            else "baixo"
        )
        student.risk_score = final_score
        student.risk_level = final_level
        student.tenant_id = tenant_id
        student.shap_top_factors = {
            "top_3": top_factors,
            "summary": format_top_factors_human(top_factors) if top_factors else "SHAP sob demanda: GET /students/{id}/risk",
            "probability": round(proba, 4), "model_score": rules["model_score"],
            "rule_flags": rules["rule_flags"], "rule_boost": rules["rule_boost"],
            "recommended_actions": rules["recommended_actions"], "confidence": rules["confidence"],
            "model_scope": model_scope,
            "model_version": str(model_version) if model_version is not None else None,
        }
        student.updated_at = evaluated_at
        session.add(RiskAssessment(
            tenant_id=tenant_id,
            student_id=student.id,
            batch_id=batch_id,
            scoring_run_id=scoring_run_id,
            evaluated_at=evaluated_at,
            score=final_score,
            risk_level=final_level,
            model_version=str(model_version) if model_version is not None else None,
            model_scope=model_scope,
            model_score=float(rules["model_score"]) if rules.get("model_score") is not None else None,
            dynamic_adjustment=dynamic_adjustment,
            features_snapshot=feature_dicts[i],
            explanation={
                "available": bool(explain),
                "top_factors": top_factors if explain else None,
                "summary": format_top_factors_human(top_factors) if top_factors else None,
                "probability": round(proba, 4),
                "rule_flags": rules["rule_flags"],
                "rule_boost": rules["rule_boost"],
                "recommended_actions": rules["recommended_actions"],
                "confidence": rules["confidence"],
            },
            context={"batch_id": batch_id, "source": "score_batch"},
        ))
        session.add(TrainingEvent(
            tenant_id=tenant_id, student_id=student.id, batch_id=batch_id,
            matricula=student.matricula, features_snapshot=feature_dicts[i],
            model_score=rules["model_score"], adjusted_score=rules["adjusted_score"],
            risk_level=rules["risk_level"], model_version=model_version, model_scope=model_scope,
        ))
        summary[final_level] = summary.get(final_level, 0) + 1
        scored_details.append({
            "matricula": student.matricula, "nome": student.nome, "risk_score": final_score,
            "risk_level": final_level, "confidence": rules["confidence"],
            "dynamic_risk_adjustment": dynamic_adjustment,
            "recommended_actions": rules["recommended_actions"][:2],
        })
    batch.status = "scored"
    batch.tenant_id = tenant_id
    batch.processed_at = datetime.now(timezone.utc)
    await session.commit()
    return {
        "batch_id": batch_id, "scored": len(students), "summary": summary,
        "students": scored_details[:20], "model_scope": model_scope, "model_version": model_version,
        "tenant_id": tenant_id, "explain": explain,
        "message": f"{len(students)} alunos pontuados via modelo {model_scope} v{model_version}",
    }


async def score_all_pending(session: AsyncSession, *, tenant_id: str, tenant_slug: str | None = None) -> dict[str, Any]:
    result = await session.execute(
        select(Student.batch_id).where(Student.risk_score.is_(None), Student.tenant_id == tenant_id).distinct()
    )
    batch_ids = [row[0] for row in result.all()]
    totals = {"baixo": 0, "medio": 0, "critico": 0, "scored": 0}
    results = []
    for bid in batch_ids:
        res = await score_batch(session, bid, tenant_id=tenant_id, tenant_slug=tenant_slug)
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
            "model_scope": "base",
            "training_data": "synthetic",
            "hybrid": "XGBoost + regras + fine-tune por tenant quando houver labels",
            "disclaimer": (
                "O modelo base foi treinado com dados sinteticos. "
                "Use como score de risco assistido + regras; nao como prediccao validada em IES real."
            ),
            "shap_on_batch_default": False,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
