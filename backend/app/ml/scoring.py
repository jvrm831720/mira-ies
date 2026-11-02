"""Orquestração do scoring — isolado por tenant, com bloqueio por qualidade de dados."""

from __future__ import annotations

from typing import Any
from datetime import datetime, timezone
from uuid import uuid4
import logging

from sqlalchemy import and_, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.student import Student, UploadBatch
from app.models.risk_assessment import RiskAssessment
from app.models.tenant import TrainingEvent, Tenant
from app.services.tenant import ensure_base_model_registered
from app.ml.data_quality import (
    FEATURE_SCHEMA_VERSION,
    assess_student_data_quality,
    require_scoreable_student,
)
from app.ml.features import build_features_from_student, features_to_dataframe
from app.ml.model import load_meta, load_model, predict_proba, probability_to_risk_score
from app.ml.explain import explain_instance, format_top_factors_human
from app.ml.rules import apply_business_rules
from app.ml.tenant_train import resolve_scoring_model, predict_proba_with_model
from app.ml.risk_semantics import RISK_SCORE_SEMANTICS_VERSION, classify_risk_score


def _safe_explain_instance(features, *, model, model_scope: str, model_version: str):
    """Falha de SHAP não invalida um score; a indisponibilidade fica explícita."""
    try:
        factors = explain_instance(
            features, top_k=3, model=model,
            model_scope=model_scope, model_version=str(model_version),
        )
        metadata = {
            "available": True, "status": "available",
            "method": "SHAP TreeExplainer",
            "explained_output": "raw_estimator_output",
            "calibration_included": False, "rules_included": False,
            "dynamic_adjustment_included": False,
            "model_scope": model_scope, "model_version": str(model_version),
        }
        return factors, metadata
    except Exception as exc:
        logging.getLogger(__name__).warning(
            "risk_explanation_unavailable",
            extra={"model_scope": model_scope, "model_version": str(model_version), "error_type": type(exc).__name__},
            exc_info=True,
        )
        return [], {
            "available": False, "status": "unavailable",
            "method": "SHAP TreeExplainer", "reason_code": "shap_calculation_failed",
            "explained_output": "raw_estimator_output",
            "calibration_included": False, "rules_included": False,
            "dynamic_adjustment_included": False,
            "model_scope": model_scope, "model_version": str(model_version),
        }


def score_student_dict(student_data: dict) -> dict[str, Any]:
    quality = require_scoreable_student(student_data)
    features = build_features_from_student(student_data)
    X = features_to_dataframe([features])
    model = load_model()
    proba = float(predict_proba(model, X)[0])
    model_score = probability_to_risk_score(proba)
    rules = apply_business_rules(features, model_score)
    meta = load_meta()
    model_version = str(meta.get("version", "unknown"))
    top_factors, explanation_metadata = _safe_explain_instance(
        features, model=model, model_scope="base", model_version=model_version
    )
    return {
        "risk_score": rules["adjusted_score"],
        "model_score": rules["model_score"],
        "risk_level": rules["risk_level"],
        "probability": round(proba, 4),
        "shap_top_factors": top_factors,
        "shap_summary": (
            format_top_factors_human(top_factors)
            if top_factors else "Explicação SHAP indisponível nesta execução."
        ),
        "features_used": features,
        "rule_flags": rules["rule_flags"],
        "rule_boost": rules["rule_boost"],
        "recommended_actions": rules["recommended_actions"],
        "confidence": rules["confidence"],
        "confidence_basis": rules["confidence_basis"],
        "missing_features": [],
        "data_quality": quality,
        "model_scope": "base",
        "model_version": model_version,
        "explanation_metadata": explanation_metadata,
        "rule_adjustments": rules["rule_adjustments"],
        "score_breakdown": {
            "model_score": rules["model_score"],
            "business_rule_adjustment_requested": rules["rule_boost"],
            "business_rule_adjustment_applied": round(rules["adjusted_score"] - rules["model_score"], 1),
            "dynamic_adjustment_requested": 0.0,
            "dynamic_adjustment_applied": 0.0,
            "final_score": rules["adjusted_score"],
        },
    }


async def score_batch(
    session: AsyncSession,
    batch_id: str,
    force: bool = False,
    *,
    tenant_id: str,
    tenant_slug: str | None = None,
    explain: bool | None = None,
    scoring_run_id: str | None = None,
) -> dict[str, Any]:
    """Pontua somente alunos com os sete campos de origem completos e válidos."""
    from app.core.config import get_settings

    settings = get_settings()
    if explain is None:
        explain = settings.shap_on_batch
    await session.execute(text("SELECT set_config('app.tenant_id', :tenant_id, true)"), {"tenant_id": tenant_id})

    tenant = (await session.execute(select(Tenant).where(Tenant.id == tenant_id))).scalar_one_or_none()
    if not tenant:
        raise ValueError("Tenant não encontrado")
    if tenant_slug and tenant.slug != tenant_slug:
        raise ValueError("tenant_slug não corresponde ao tenant_id")

    batch = (await session.execute(
        select(UploadBatch).where(UploadBatch.id == batch_id, UploadBatch.tenant_id == tenant_id)
    )).scalar_one_or_none()
    if not batch:
        raise ValueError(f"Batch {batch_id} não encontrado")

    run_id = scoring_run_id or str(uuid4())
    replay_rows = (await session.execute(
        select(RiskAssessment).where(
            RiskAssessment.tenant_id == tenant_id,
            RiskAssessment.batch_id == batch_id,
            RiskAssessment.scoring_run_id == run_id,
        )
    )).scalars().all()
    if replay_rows:
        replay_summary = {"baixo": 0, "medio": 0, "critico": 0}
        for assessment in replay_rows:
            replay_summary[assessment.risk_level] = replay_summary.get(assessment.risk_level, 0) + 1
        return {
            "batch_id": batch_id, "scored": len(replay_rows), "summary": replay_summary,
            "scoring_run_id": run_id, "idempotent_replay": True,
            "model_scope": replay_rows[0].model_scope, "model_version": replay_rows[0].model_version,
            "indeterminate_count": 0, "tenant_id": tenant_id,
            "message": "Execução já registrada; nenhuma avaliação duplicada foi criada.",
        }

    query = select(Student).where(Student.batch_id == batch_id, Student.tenant_id == tenant_id)
    if not force:
        legacy_schema = Student.shap_top_factors["feature_schema_version"].astext.is_(None) | (
            Student.shap_top_factors["feature_schema_version"].astext != FEATURE_SCHEMA_VERSION
        )
        if batch.status == "processed":
            query = query.where(Student.risk_score.is_(None))
        else:
            # One-time migration-by-reassessment: legacy scores without the new
            # schema marker are rechecked, even if they previously had a score.
            query = query.where(legacy_schema)
    students = list((await session.execute(query)).scalars().all())
    if not students:
        return {
            "batch_id": batch_id, "scored": 0, "indeterminate_count": 0,
            "message": "Nenhum aluno pendente", "summary": {"baixo": 0, "medio": 0, "critico": 0},
        }

    evaluated_at = datetime.now(timezone.utc)
    eligible: list[Student] = []
    feature_dicts: list[dict[str, float]] = []
    indeterminate: list[dict[str, Any]] = []
    for student in students:
        quality = assess_student_data_quality(student)
        if not quality["can_score"]:
            # No score or risk level is manufactured. The latest state carries
            # actionable coverage diagnostics and can be replaced by a later import.
            student.risk_score = None
            student.risk_level = None
            student.model_risk_score = None
            student.shap_top_factors = {
                "evaluation_status": "indeterminate",
                "feature_schema_version": FEATURE_SCHEMA_VERSION,
                "evaluated_at": evaluated_at.isoformat(),
                "source_batch_id": batch_id,
                "data_quality": quality,
                "summary": "Avaliação indeterminada: dados insuficientes para calcular risco.",
            }
            indeterminate.append({
                "matricula": student.matricula,
                "nome": student.nome,
                "evaluation_status": "indeterminate",
                "data_quality": quality,
            })
            continue
        eligible.append(student)
        feature_dicts.append(build_features_from_student(student))

    summary = {"baixo": 0, "medio": 0, "critico": 0}
    scored_details: list[dict[str, Any]] = []
    model_scope = None
    model_version = None

    if eligible:
        await ensure_base_model_registered(session)
        model, calibrator, model_scope, model_version = await resolve_scoring_model(session, tenant)
        X = features_to_dataframe(feature_dicts)
        probas = predict_proba_with_model(model, X, calibrator)

        for index, student in enumerate(eligible):
            features = feature_dicts[index]
            quality = assess_student_data_quality(student)
            proba = float(probas[index])
            model_score = probability_to_risk_score(proba)
            rules = apply_business_rules(features, model_score)
            if explain:
                top_factors, explanation_metadata = _safe_explain_instance(
                    features, model=model, model_scope=model_scope,
                    model_version=str(model_version),
                )
            else:
                top_factors = []
                explanation_metadata = {
                    "available": False, "status": "not_requested",
                    "method": "SHAP TreeExplainer", "reason_code": "explanation_not_requested",
                    "calibration_included": False, "rules_included": False,
                    "dynamic_adjustment_included": False,
                    "model_scope": model_scope, "model_version": str(model_version),
                }
            dynamic_adjustment = float(student.dynamic_risk_adjustment or 0.0)
            final_score = round(min(100.0, max(0.0, rules["adjusted_score"] + dynamic_adjustment)), 1)
            final_level = classify_risk_score(final_score)

            student.model_risk_score = rules["adjusted_score"]
            student.risk_score = final_score
            student.risk_level = final_level
            student.tenant_id = tenant_id
            student.shap_top_factors = {
                "evaluation_status": "scored",
                "top_3": top_factors,
                "summary": format_top_factors_human(top_factors) if top_factors else "Explicação SHAP não calculada nesta execução.",
                "probability": round(proba, 4),
                "model_score": rules["model_score"],
                "rule_flags": rules["rule_flags"],
                "rule_boost": rules["rule_boost"],
                "recommended_actions": rules["recommended_actions"],
                "confidence": rules["confidence"],
                "confidence_basis": rules["confidence_basis"],
                "rule_adjustments": rules["rule_adjustments"],
                "score_breakdown": {
                    "model_score": rules["model_score"],
                    "business_rule_adjustment_requested": rules["rule_boost"],
                    "business_rule_adjustment_applied": round(rules["adjusted_score"] - rules["model_score"], 1),
                    "dynamic_adjustment_requested": dynamic_adjustment,
                    "dynamic_adjustment_applied": round(final_score - rules["adjusted_score"], 1),
                    "final_score": final_score,
                },
                "explanation_metadata": explanation_metadata,
                "model_scope": model_scope,
                "model_version": str(model_version) if model_version is not None else None,
                "data_quality": quality,
                "feature_schema_version": FEATURE_SCHEMA_VERSION,
            }
            student.updated_at = evaluated_at
            session.add(RiskAssessment(
                tenant_id=tenant_id,
                student_id=student.id,
                batch_id=batch_id,
                scoring_run_id=run_id,
                evaluated_at=evaluated_at,
                score=final_score,
                risk_level=final_level,
                model_version=str(model_version) if model_version is not None else None,
                score_semantics_version=RISK_SCORE_SEMANTICS_VERSION,
                score_basis="final",
                model_scope=model_scope,
                model_score=float(rules["model_score"]),
                dynamic_adjustment=dynamic_adjustment,
                features_snapshot={**features, "__data_quality__": quality, "__feature_schema_version__": FEATURE_SCHEMA_VERSION},
                explanation={
                    "available": bool(top_factors),
                    "top_factors": top_factors if explain else None,
                    "summary": format_top_factors_human(top_factors) if top_factors else None,
                    "probability": round(proba, 4),
                    "rule_flags": rules["rule_flags"],
                    "rule_boost": rules["rule_boost"],
                    "rule_adjustments": rules["rule_adjustments"],
                    "recommended_actions": rules["recommended_actions"],
                    "confidence": rules["confidence"],
                    "confidence_basis": rules["confidence_basis"],
                    "score_breakdown": {
                        "model_score": rules["model_score"],
                        "business_rule_adjustment_requested": rules["rule_boost"],
                        "business_rule_adjustment_applied": round(rules["adjusted_score"] - rules["model_score"], 1),
                        "dynamic_adjustment_requested": dynamic_adjustment,
                        "dynamic_adjustment_applied": round(final_score - rules["adjusted_score"], 1),
                        "final_score": final_score,
                    },
                    "explanation_metadata": explanation_metadata,
                    "data_quality": quality,
                },
                context={"batch_id": batch_id, "source": "score_batch", "feature_schema_version": FEATURE_SCHEMA_VERSION},
            ))
            session.add(TrainingEvent(
                tenant_id=tenant_id, student_id=student.id, batch_id=batch_id,
                matricula=student.matricula, scored_at=evaluated_at,
                features_snapshot=features, model_score=rules["model_score"],
                adjusted_score=rules["adjusted_score"], risk_level=rules["risk_level"],
                model_version=model_version, model_scope=model_scope,
            ))
            summary[final_level] = summary.get(final_level, 0) + 1
            scored_details.append({
                "matricula": student.matricula, "nome": student.nome,
                "risk_score": final_score, "risk_level": final_level,
                "confidence": rules["confidence"],
                "rule_adjustments": rules["rule_adjustments"],
                "score_breakdown": {
                    "model_score": rules["model_score"],
                    "business_rule_adjustment_requested": rules["rule_boost"],
                    "business_rule_adjustment_applied": round(rules["adjusted_score"] - rules["model_score"], 1),
                    "dynamic_adjustment_requested": dynamic_adjustment,
                    "dynamic_adjustment_applied": round(final_score - rules["adjusted_score"], 1),
                    "final_score": final_score,
                },
                "dynamic_risk_adjustment": dynamic_adjustment,
                "recommended_actions": rules["recommended_actions"][:2],
            })

    # "scored" means the batch scoring pass completed. Individual students may
    # remain indeterminate; their data-quality state is persisted per student.
    batch.status = "scored"
    batch.tenant_id = tenant_id
    batch.processed_at = evaluated_at
    try:
        await session.commit()
    except Exception as exc:
        await session.rollback()
        logging.getLogger(__name__).exception(
            "risk_assessment_persistence_failed",
            extra={"tenant_id": tenant_id, "batch_id": batch_id, "scoring_run_id": run_id},
        )
        raise RuntimeError("Falha ao persistir avaliações de risco; o lote não foi confirmado.") from exc

    return {
        "batch_id": batch_id,
        "scored": len(eligible),
        "indeterminate_count": len(indeterminate),
        "indeterminate_students": indeterminate[:50],
        "summary": summary,
        "scoring_run_id": run_id,
        "idempotent_replay": False,
        "students": scored_details[:20],
        "model_scope": model_scope,
        "model_version": model_version,
        "tenant_id": tenant_id,
        "explain": explain,
        "evaluation_status": "indeterminate" if not eligible else ("partial" if indeterminate else "complete"),
        "message": (
            f"{len(eligible)} alunos pontuados; {len(indeterminate)} sem dados suficientes."
            if indeterminate
            else f"{len(eligible)} alunos pontuados via modelo {model_scope} v{model_version}"
        ),
    }


async def score_all_pending(session: AsyncSession, *, tenant_id: str, tenant_slug: str | None = None) -> dict[str, Any]:
    result = await session.execute(
        select(Student.batch_id)
        .join(UploadBatch, UploadBatch.id == Student.batch_id)
        .where(
            Student.tenant_id == tenant_id,
            UploadBatch.tenant_id == tenant_id,
            or_(
                and_(UploadBatch.status == "processed", Student.risk_score.is_(None)),
                and_(
                    UploadBatch.status == "scored",
                    or_(
                        Student.shap_top_factors["feature_schema_version"].astext.is_(None),
                        Student.shap_top_factors["feature_schema_version"].astext != FEATURE_SCHEMA_VERSION,
                    ),
                ),
            ),
        )
        .distinct()
    )
    batch_ids = [row[0] for row in result.all()]
    totals = {"baixo": 0, "medio": 0, "critico": 0, "scored": 0, "indeterminate": 0}
    results = []
    for batch_id in batch_ids:
        result_item = await score_batch(session, batch_id, tenant_id=tenant_id, tenant_slug=tenant_slug)
        totals["scored"] += result_item["scored"]
        totals["indeterminate"] += result_item.get("indeterminate_count", 0)
        for level in ("baixo", "medio", "critico"):
            totals[level] += result_item["summary"].get(level, 0)
        results.append(result_item)
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
                "O modelo base foi treinado com dados sintéticos. "
                "Use como score de risco assistido + regras; não como predição validada em IES real."
            ),
            "shap_on_batch_default": False,
            "feature_schema_version": FEATURE_SCHEMA_VERSION,
            "feature_columns": list(__import__("app.ml.features", fromlist=["FEATURE_COLUMNS"]).FEATURE_COLUMNS),
            "feature_labels_pt": dict(__import__("app.ml.features", fromlist=["FEATURE_LABELS_PT"]).FEATURE_LABELS_PT),
            "risk_score_semantics_version": RISK_SCORE_SEMANTICS_VERSION,
            "risk_score_bands": {"baixo": {"min": 0, "max_exclusive": 40}, "medio": {"min": 40, "max_exclusive": 70}, "critico": {"min": 70, "max": 100}},
            "required_source_fields": list(__import__("app.ml.data_quality", fromlist=["REQUIRED_SOURCE_FIELDS"]).REQUIRED_SOURCE_FIELDS),
        }
    except Exception as exc:
        return {"status": "error", "message": str(exc)}
