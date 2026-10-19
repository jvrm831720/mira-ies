"""
Fine-tune / treino supervisionado por tenant (Modelo Hibrido C — ciclo 2).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score, average_precision_score, brier_score_loss, classification_report
from sklearn.calibration import CalibratedClassifierCV
import xgboost as xgb
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ml.features import FEATURE_COLUMNS, FEATURE_LABELS_PT, build_features_from_student
from app.ml.model import MODELS_DIR, _generate_synthetic_training_data, load_meta, invalidate_cache
from app.models.tenant import Tenant, TrainingEvent, ModelArtifact
from app.services.tenant import MIN_LABELED_EVENTS, MIN_POSITIVE_LABELS, refresh_tenant_readiness

MIN_TRAIN_SAMPLES = 50
MIN_TRAIN_POSITIVES = 5

_tenant_model_cache: dict[str, Any] = {}
_tenant_cal_cache: dict[str, Any] = {}


def _events_to_dataframe(events: list) -> pd.DataFrame:
    rows = []
    for e in events:
        snap = dict(e.features_snapshot or {})
        feats = build_features_from_student(snap)
        feats["label"] = int(e.label) if e.label is not None else None
        rows.append(feats)
    df = pd.DataFrame(rows)
    for col in FEATURE_COLUMNS:
        if col not in df.columns:
            df[col] = 0.0
    return df


def _blend_with_synthetic(df_tenant: pd.DataFrame, seed: int = 42) -> pd.DataFrame:
    n = len(df_tenant)
    if n >= MIN_LABELED_EVENTS:
        return df_tenant
    need = max(MIN_LABELED_EVENTS - n, 100)
    synth = _generate_synthetic_training_data(n_samples=need, seed=seed)
    synth = synth[FEATURE_COLUMNS + ["risco_alto"]].rename(columns={"risco_alto": "label"})
    tenant_boost = pd.concat([df_tenant, df_tenant], ignore_index=True)
    blended = pd.concat([tenant_boost, synth], ignore_index=True)
    return blended.sample(frac=1.0, random_state=seed).reset_index(drop=True)


def _train_xgb(df: pd.DataFrame, seed: int = 42):
    X = df[FEATURE_COLUMNS]
    y = df["label"].astype(int)
    can_stratify = y.nunique() > 1 and y.value_counts().min() >= 2
    if len(df) >= 40 and can_stratify:
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=seed, stratify=y)
    else:
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=seed)

    model = xgb.XGBClassifier(
        n_estimators=150, max_depth=4, learning_rate=0.07, subsample=0.85,
        colsample_bytree=0.8, reg_lambda=1.5, reg_alpha=0.4, min_child_weight=5,
        gamma=0.15, objective="binary:logistic", eval_metric="logloss",
        random_state=seed, n_jobs=-1,
        scale_pos_weight=float((y_train == 0).sum() / max(1, (y_train == 1).sum())),
    )
    model.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)

    calibrator = None
    try:
        if y_test.nunique() > 1:
            calibrator = CalibratedClassifierCV(model, method="isotonic", cv="prefit")
            calibrator.fit(X_test, y_test)
            y_prob = calibrator.predict_proba(X_test)[:, 1]
        else:
            y_prob = model.predict_proba(X_test)[:, 1]
    except Exception:
        y_prob = model.predict_proba(X_test)[:, 1]

    y_pred = (y_prob >= 0.5).astype(int)
    metrics: dict[str, Any] = {"n_train": int(len(X_train)), "n_test": int(len(X_test)), "positive_rate": float(y.mean())}
    try:
        metrics["auc"] = float(roc_auc_score(y_test, y_prob))
    except Exception:
        metrics["auc"] = None
    try:
        metrics["average_precision"] = float(average_precision_score(y_test, y_prob))
    except Exception:
        metrics["average_precision"] = None
    try:
        metrics["brier_score"] = float(brier_score_loss(y_test, y_prob))
    except Exception:
        metrics["brier_score"] = None
    try:
        report = classification_report(y_test, y_pred, output_dict=True, zero_division=0)
        metrics["accuracy"] = float(report.get("accuracy", 0))
        if "1" in report:
            metrics["precision_risco"] = float(report["1"]["precision"])
            metrics["recall_risco"] = float(report["1"]["recall"])
            metrics["f1_risco"] = float(report["1"]["f1-score"])
    except Exception:
        pass
    importance = model.feature_importances_
    metrics["top_features"] = sorted([
        {"feature": f, "label": FEATURE_LABELS_PT.get(f, f), "importance": round(float(i), 4)}
        for f, i in zip(FEATURE_COLUMNS, importance)
    ], key=lambda x: -x["importance"])[:5]
    return model, calibrator, metrics


def _should_activate(tenant_metrics, base_auc, *, force_activate=False):
    if force_activate:
        return True, "Ativado com force_activate=true"
    auc = tenant_metrics.get("auc")
    if auc is None:
        return False, "AUC indisponivel — modelo salvo mas nao ativado"
    if base_auc is None:
        if auc >= 0.65:
            return True, f"AUC tenant={auc:.3f} (sem baseline) >= 0.65"
        return False, f"AUC tenant={auc:.3f} < 0.65"
    if auc >= base_auc - 0.02:
        return True, f"AUC tenant={auc:.3f} >= base={base_auc:.3f}-0.02"
    return False, f"AUC tenant={auc:.3f} < base={base_auc:.3f} — mantem base ativo"


async def train_tenant_model(session: AsyncSession, *, tenant_slug: str = "default", force: bool = False, force_activate: bool = False, seed: int = 42) -> dict[str, Any]:
    result = await session.execute(select(Tenant).where(Tenant.slug == tenant_slug))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise ValueError(f"Tenant '{tenant_slug}' nao encontrado. Crie com POST /tenants.")

    await refresh_tenant_readiness(session, tenant.id)

    if not force and not tenant.tenant_model_ready:
        return {
            "status": "not_ready",
            "message": f"Tenant nao pronto. Labels={tenant.labeled_events_count}/{MIN_LABELED_EVENTS}, positivos={tenant.positive_labels_count}/{MIN_POSITIVE_LABELS}. Use force=true.",
            "tenant_id": tenant.id, "slug": tenant.slug,
            "labeled_events": tenant.labeled_events_count,
            "positive_labels": tenant.positive_labels_count,
        }

    q = await session.execute(select(TrainingEvent).where(TrainingEvent.tenant_id == tenant.id, TrainingEvent.label.is_not(None)))
    events = list(q.scalars().all())
    n_pos = sum(1 for e in events if e.label == 1)
    n_neg = sum(1 for e in events if e.label == 0)

    if len(events) < MIN_TRAIN_SAMPLES and not force:
        raise ValueError(f"Poucos eventos ({len(events)} < {MIN_TRAIN_SAMPLES}). Use force=true.")
    if n_pos < MIN_TRAIN_POSITIVES and not force:
        raise ValueError(f"Poucos positivos ({n_pos} < {MIN_TRAIN_POSITIVES}). Use force=true.")
    if len(events) < 10:
        raise ValueError("Minimo absoluto: 10 eventos rotulados.")

    df_tenant = _events_to_dataframe(events).dropna(subset=["label"])
    df_train = _blend_with_synthetic(df_tenant, seed=seed)
    model, calibrator, metrics = _train_xgb(df_train, seed=seed)
    metrics["n_tenant_events"] = len(events)
    metrics["n_tenant_positive"] = n_pos
    metrics["n_tenant_negative"] = n_neg
    metrics["blended"] = len(df_train) > len(df_tenant)

    tenant_dir = MODELS_DIR / "tenants" / tenant.slug
    tenant_dir.mkdir(parents=True, exist_ok=True)
    version = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    model_path = tenant_dir / f"model_{version}.joblib"
    cal_path = tenant_dir / f"calibrator_{version}.joblib"
    joblib.dump(model, model_path)
    if calibrator is not None:
        joblib.dump(calibrator, cal_path)
    (tenant_dir / f"meta_{version}.json").write_text(json.dumps({**metrics, "feature_columns": FEATURE_COLUMNS, "version": version}, indent=2), encoding="utf-8")

    try:
        base_auc = load_meta().get("auc")
    except Exception:
        base_auc = None

    activate, reason = _should_activate(metrics, base_auc, force_activate=force_activate)

    if activate:
        prev = await session.execute(select(ModelArtifact).where(ModelArtifact.tenant_id == tenant.id, ModelArtifact.scope == "tenant", ModelArtifact.is_active == True))  # noqa: E712
        for art in prev.scalars().all():
            art.is_active = False

    artifact = ModelArtifact(
        id=str(uuid4()), tenant_id=tenant.id, name=f"beacon-tenant-{tenant.slug}",
        version=version, scope="tenant", storage_path=str(model_path),
        metrics=metrics, feature_columns=FEATURE_COLUMNS, is_active=activate,
        trained_at=datetime.now(timezone.utc),
    )
    session.add(artifact)
    await session.flush()
    if activate:
        tenant.active_model_id = artifact.id
    await session.commit()
    invalidate_tenant_cache(tenant.slug)

    return {
        "status": "trained", "activated": activate, "activation_reason": reason,
        "tenant_id": tenant.id, "slug": tenant.slug, "artifact_id": artifact.id,
        "version": version, "storage_path": str(model_path),
        "metrics": {k: metrics.get(k) for k in ["auc", "average_precision", "brier_score", "accuracy", "n_tenant_events", "n_tenant_positive", "blended", "top_features"]},
        "base_auc": base_auc,
        "message": f"Modelo tenant treinado e {'ATIVADO' if activate else 'salvo (nao ativado)'}. {reason}",
    }


def invalidate_tenant_cache(slug: str | None = None):
    global _tenant_model_cache, _tenant_cal_cache
    if slug is None:
        _tenant_model_cache.clear()
        _tenant_cal_cache.clear()
    else:
        _tenant_model_cache.pop(slug, None)
        _tenant_cal_cache.pop(slug, None)


def load_tenant_model_from_path(storage_path: str, slug: str):
    global _tenant_model_cache
    if slug in _tenant_model_cache:
        return _tenant_model_cache[slug]
    path = Path(storage_path)
    if not path.exists():
        return None
    model = joblib.load(path)
    _tenant_model_cache[slug] = model
    version = path.stem.replace("model_", "")
    cal_path = path.parent / f"calibrator_{version}.joblib"
    if cal_path.exists():
        _tenant_cal_cache[slug] = joblib.load(cal_path)
    return model


def get_tenant_calibrator(slug: str):
    return _tenant_cal_cache.get(slug)


async def resolve_scoring_model(session: AsyncSession, tenant: Tenant):
    from app.ml.model import load_model, load_calibrator
    if tenant.active_model_id:
        r = await session.execute(select(ModelArtifact).where(ModelArtifact.id == tenant.active_model_id, ModelArtifact.is_active == True))  # noqa: E712
        art = r.scalar_one_or_none()
        if art and art.storage_path:
            model = load_tenant_model_from_path(art.storage_path, tenant.slug)
            if model is not None:
                return model, get_tenant_calibrator(tenant.slug), "tenant", art.version
    model = load_model()
    try:
        cal = load_calibrator()
    except Exception:
        cal = None
    try:
        version = str(load_meta().get("version", "base"))
    except Exception:
        version = "base"
    return model, cal, "base", version


def predict_proba_with_model(model, X: pd.DataFrame, calibrator=None) -> np.ndarray:
    X = X[FEATURE_COLUMNS]
    if calibrator is not None:
        try:
            return calibrator.predict_proba(X)[:, 1]
        except Exception:
            pass
    return model.predict_proba(X)[:, 1]
