"""Fine-tune / treino supervisionado por tenant (Modelo Hibrido C — ciclo 2)."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score, average_precision_score, brier_score_loss, classification_report
from sklearn.calibration import CalibratedClassifierCV
import xgboost as xgb
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.ml.features import FEATURE_COLUMNS, FEATURE_LABELS_PT, build_features_from_student
from app.ml.model import MODELS_DIR, _generate_synthetic_training_data, load_calibrator, load_meta, load_model
from app.ml.storage import get_model_storage
from app.ml.targets import TARGET_DEFINITION_VERSION, TARGET_HORIZON
from app.models.tenant import Tenant, TrainingEvent, ModelArtifact
from app.services.tenant import MIN_LABELED_EVENTS, MIN_POSITIVE_LABELS, refresh_tenant_readiness
from app.services.training_policy import (
    resolve_institutional_training_authorization,
    resolve_training_policy,
)

MIN_TRAIN_SAMPLES = 50
MIN_TRAIN_POSITIVES = 5
_tenant_model_cache: dict[str, Any] = {}
_tenant_cal_cache: dict[str, Any] = {}

_SAFE_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def _safe_tenant_dirname(slug: str) -> str:
    """Valida o slug antes de usa-lo como componente de path no storage de modelos."""
    if not _SAFE_SLUG_RE.match(slug or ""):
        raise ValueError(f"tenant slug invalido para storage de modelo: {slug!r}")
    return slug


def _events_to_dataframe(events: list) -> pd.DataFrame:
    rows = []
    for e in events:
        snap = dict(e.features_snapshot or {})
        feats = build_features_from_student(snap)
        feats["label"] = int(e.label) if e.label is not None else None
        # Student.id pode mudar entre uploads; a matrícula é a chave estável dentro do tenant.
        matricula_key = str(e.matricula or "").strip().casefold()
        if not matricula_key:
            raise ValueError("Treino temporal requer matrícula não vazia para agrupar eventos do aluno.")
        feats["__group_id"] = matricula_key
        feats["__scored_at"] = e.scored_at
        feats["__outcome_at"] = e.outcome_at
        rows.append(feats)
    df = pd.DataFrame(rows)
    for col in FEATURE_COLUMNS:
        if col not in df.columns:
            df[col] = 0.0
    return df


def _split_tenant_events(
    df_tenant: pd.DataFrame, seed: int = 42
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Separa períodos futuros e alunos, com embargo de maturação do alvo.

    Sintéticos só são adicionados depois, exclusivamente ao treino. Datas sucessivas
    e observações amadurecidas impedem vazamento temporal pelo horizonte de 90 dias.
    """
    del seed  # o corte é cronológico e determinístico, não aleatório
    df = df_tenant.copy()
    df["__scored_at"] = pd.to_datetime(df["__scored_at"], utc=True, errors="coerce")
    df["__outcome_at"] = pd.to_datetime(df["__outcome_at"], utc=True, errors="coerce")
    if df[["__scored_at", "__outcome_at", "__group_id"]].isna().any().any():
        raise ValueError(
            "Treino temporal requer scored_at, outcome_at e identificador de aluno em todos os eventos."
        )
    if (df["__outcome_at"] < df["__scored_at"]).any():
        raise ValueError("Treino temporal encontrou outcome_at anterior a scored_at.")
    bounds = df.groupby("__group_id", sort=False).agg(
        score_start=("__scored_at", "min"),
        score_end=("__scored_at", "max"),
        outcome_end=("__outcome_at", "max"),
    )
    if len(bounds) < 5 or df["label"].nunique() < 2:
        raise ValueError(
            "Treino temporal requer ao menos 5 alunos distintos e exemplos das duas classes."
        )

    # Pesquise todos os cortes quando há até 101 datas distintas; para históricos
    # maiores, use uma grade cronológica densa e limitada para custo previsível.
    ordered_cuts = bounds["score_end"].drop_duplicates().sort_values().reset_index(drop=True)
    if len(ordered_cuts) > 101:
        candidate_indexes = np.linspace(0, len(ordered_cuts) - 1, num=101, dtype=int)
        ordered_cuts = ordered_cuts.iloc[candidate_indexes].drop_duplicates().reset_index(drop=True)

    label_counts = df.groupby("__group_id")["label"].agg(
        n_events="size",
        n_positive=lambda labels: int((labels == 1).sum()),
        n_negative=lambda labels: int((labels == 0).sum()),
    )
    bounds = bounds.join(label_counts)
    best_candidate = None
    for train_cut in ordered_cuts:
        calibration_available_at = train_cut + TARGET_HORIZON
        train_mask = (
            (bounds["score_end"] <= train_cut)
            & (bounds["outcome_end"] <= calibration_available_at)
        )
        train_groups = bounds[train_mask]
        if len(train_groups) < 2 or not train_groups["n_positive"].sum() or not train_groups["n_negative"].sum():
            continue

        for calibration_cut in ordered_cuts[ordered_cuts > calibration_available_at]:
            test_available_at = calibration_cut + TARGET_HORIZON
            calibration_mask = (
                (bounds["score_start"] > calibration_available_at)
                & (bounds["score_end"] <= calibration_cut)
                & (bounds["outcome_end"] <= test_available_at)
            )
            test_mask = bounds["score_start"] > test_available_at
            calibration_groups = bounds[calibration_mask]
            test_groups = bounds[test_mask]
            groups = (train_groups, calibration_groups, test_groups)
            if any(len(part) < 2 or not part["n_positive"].sum() or not part["n_negative"].sum() for part in groups):
                continue

            row_counts = [int(part["n_events"].sum()) for part in groups]
            total = sum(row_counts)
            ratios = [count / total for count in row_counts]
            ratio_error = sum(abs(actual - target) for actual, target in zip(ratios, (0.60, 0.20, 0.20)))
            candidate = (
                ratio_error,
                -total,
                train_groups.index,
                calibration_groups.index,
                test_groups.index,
            )
            if best_candidate is None or candidate[:2] < best_candidate[:2]:
                best_candidate = candidate

    if best_candidate:
        _, _, train_ids, calibration_ids, test_ids = best_candidate
        return tuple(
            df[df["__group_id"].isin(ids)].reset_index(drop=True)
            for ids in (train_ids, calibration_ids, test_ids)
        )

    raise ValueError(
        "Não foi possível formar períodos cronológicos de treino, calibração e teste "
        "com as duas classes sem separar ou reutilizar alunos. Colete mais histórico real."
    )


def _blend_with_synthetic(df_tenant_train: pd.DataFrame, seed: int = 42) -> pd.DataFrame:
    n = len(df_tenant_train)
    if n >= MIN_LABELED_EVENTS:
        return df_tenant_train
    need = max(MIN_LABELED_EVENTS - n, 100)
    synth = _generate_synthetic_training_data(n_samples=need, seed=seed)
    synth = synth[FEATURE_COLUMNS + ["risco_alto"]].rename(columns={"risco_alto": "label"})
    tenant_boost = pd.concat([df_tenant_train, df_tenant_train], ignore_index=True)
    return pd.concat([tenant_boost, synth], ignore_index=True).sample(frac=1.0, random_state=seed).reset_index(drop=True)


def _train_xgb(
    df_train: pd.DataFrame, df_calibration: pd.DataFrame, df_test: pd.DataFrame, seed: int = 42
):
    """Treina, calibra e avalia em conjuntos reais disjuntos do tenant."""
    X_train, y_train = df_train[FEATURE_COLUMNS], df_train["label"].astype(int)
    X_cal, y_cal = df_calibration[FEATURE_COLUMNS], df_calibration["label"].astype(int)
    X_test, y_test = df_test[FEATURE_COLUMNS], df_test["label"].astype(int)
    model = xgb.XGBClassifier(
        n_estimators=150, max_depth=4, learning_rate=0.07, subsample=0.85,
        colsample_bytree=0.8, reg_lambda=1.5, reg_alpha=0.4, min_child_weight=5,
        gamma=0.15, objective="binary:logistic", eval_metric="logloss",
        random_state=seed, n_jobs=-1,
        scale_pos_weight=float((y_train == 0).sum() / max(1, (y_train == 1).sum())),
    )
    model.fit(X_train, y_train, verbose=False)
    calibrator = None
    try:
        if y_cal.nunique() > 1:
            calibrator = CalibratedClassifierCV(model, method="sigmoid", cv="prefit")
            calibrator.fit(X_cal, y_cal)
            y_prob = calibrator.predict_proba(X_test)[:, 1]
        else:
            y_prob = model.predict_proba(X_test)[:, 1]
    except Exception:
        y_prob = model.predict_proba(X_test)[:, 1]
    y_pred = (y_prob >= 0.5).astype(int)
    metrics: dict[str, Any] = {
        "n_train": int(len(X_train)), "n_calibration": int(len(X_cal)), "n_test": int(len(X_test)),
        "positive_rate": float(y_test.mean()),
        "evaluation_split": "temporal_group_holdout_with_90d_embargo",
        "train_period_end": str(pd.to_datetime(df_train["__scored_at"], utc=True, errors="coerce").max()),
        "train_label_observation_end": str(pd.to_datetime(df_train["__outcome_at"], utc=True, errors="coerce").max()),
        "calibration_period_start": str(pd.to_datetime(df_calibration["__scored_at"], utc=True, errors="coerce").min()),
        "calibration_period_end": str(pd.to_datetime(df_calibration["__scored_at"], utc=True, errors="coerce").max()),
        "calibration_label_observation_end": str(pd.to_datetime(df_calibration["__outcome_at"], utc=True, errors="coerce").max()),
        "test_period_start": str(pd.to_datetime(df_test["__scored_at"], utc=True, errors="coerce").min()),
        "test_label_observation_end": str(pd.to_datetime(df_test["__outcome_at"], utc=True, errors="coerce").max()),
        "calibration_method": "sigmoid" if calibrator is not None else None,
    }
    try:
        metrics["auc"] = float(roc_auc_score(y_test, y_prob))
    except Exception:
        metrics["auc"] = None
    metrics["training_data"] = "labeled+synthetic_blend"
    metrics["model_scope"] = "tenant"
    metrics["disclaimer"] = (
        "Alvo evasion_90d_v1; holdout temporal por aluno com embargo de maturação de 90 dias. "
        "Ainda nao e validacao externa nem deve orientar intervencoes sem revisao humana."
    )
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
    settings = get_settings()
    if force and not settings.allow_force_train:
        raise ValueError("force=true bloqueado (ALLOW_FORCE_TRAIN=false). Aguarde limiar de labels.")
    if force_activate and not settings.allow_force_activate:
        raise ValueError("force_activate=true bloqueado (ALLOW_FORCE_ACTIVATE=false). Ativacao so com AUC >= base.")

    result = await session.execute(select(Tenant).where(Tenant.slug == tenant_slug))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise ValueError(f"Tenant '{tenant_slug}' nao encontrado.")

    # Authorization is checked before readiness refresh or any model training.
    # Existing scoring/inference paths do not call this function and are unaffected.
    authorization = await resolve_institutional_training_authorization(
        session, tenant_id=tenant.id
    )
    if not authorization.allowed:
        raise ValueError(
            "Treino institucional bloqueado por governanca: "
            f"{authorization.reason}"
        )

    await refresh_tenant_readiness(session, tenant.id)

    if not force and not tenant.tenant_model_ready:
        return {
            "status": "not_ready",
            "message": f"Tenant nao pronto. Labels={tenant.labeled_events_count}/{MIN_LABELED_EVENTS}, positivos={tenant.positive_labels_count}/{MIN_POSITIVE_LABELS}.",
            "tenant_id": tenant.id, "slug": tenant.slug,
            "labeled_events": tenant.labeled_events_count,
            "positive_labels": tenant.positive_labels_count,
        }

    q = await session.execute(select(TrainingEvent).where(
        TrainingEvent.tenant_id == tenant.id,
        TrainingEvent.label.is_not(None),
        TrainingEvent.target_definition == TARGET_DEFINITION_VERSION,
    ))
    events = list(q.scalars().all())
    decision = await resolve_training_policy(
        session,
        tenant_id=tenant.id,
        purpose="institutional_training",
        dataset_eligible=bool(events) and all(
            e.tenant_id == tenant.id
            and e.label is not None
            and e.target_definition == TARGET_DEFINITION_VERSION
            for e in events
        ),
        institutional_use_authorized=authorization.allowed,
    )
    if not decision.allowed:
        raise ValueError(
            "Treino institucional bloqueado por governanca: "
            f"{decision.reason}"
        )

    n_pos = sum(1 for e in events if e.label == 1)
    n_neg = sum(1 for e in events if e.label == 0)

    if len(events) < MIN_TRAIN_SAMPLES and not force:
        raise ValueError(f"Poucos eventos ({len(events)} < {MIN_TRAIN_SAMPLES}).")
    if n_pos < MIN_TRAIN_POSITIVES and not force:
        raise ValueError(f"Poucos positivos ({n_pos} < {MIN_TRAIN_POSITIVES}).")
    if len(events) < 10:
        raise ValueError("Minimo absoluto: 10 eventos rotulados.")

    df_tenant = _events_to_dataframe(events).dropna(subset=["label"])
    df_tenant_train, df_tenant_cal, df_tenant_test = _split_tenant_events(df_tenant, seed=seed)
    df_train = _blend_with_synthetic(df_tenant_train, seed=seed)
    model, calibrator, metrics = _train_xgb(df_train, df_tenant_cal, df_tenant_test, seed=seed)
    metrics["n_tenant_events"] = len(events)
    metrics["n_tenant_positive"] = n_pos
    metrics["n_tenant_negative"] = n_neg
    metrics["target_definition"] = TARGET_DEFINITION_VERSION
    metrics["blended"] = len(df_train) > len(df_tenant_train)
    metrics["n_labeled_real"] = len(events)
    metrics["n_tenant_train_real_events"] = len(df_tenant_train)
    metrics["n_tenant_calibration_real_events"] = len(df_tenant_cal)
    metrics["n_tenant_test_real_events"] = len(df_tenant_test)
    metrics["n_synthetic_training_rows"] = int(df_train["__group_id"].isna().sum())
    metrics["n_repeated_tenant_training_rows"] = max(
        0, int(df_train["__group_id"].notna().sum()) - len(df_tenant_train)
    )
    n_temporal_evaluation = len(df_tenant_train) + len(df_tenant_cal) + len(df_tenant_test)
    metrics["n_temporal_evaluation_events"] = n_temporal_evaluation
    metrics["temporal_train_ratio"] = round(len(df_tenant_train) / n_temporal_evaluation, 4)
    metrics["temporal_calibration_ratio"] = round(len(df_tenant_cal) / n_temporal_evaluation, 4)
    metrics["temporal_test_ratio"] = round(len(df_tenant_test) / n_temporal_evaluation, 4)
    metrics["n_tenant_test_real"] = len(df_tenant_test)
    metrics["n_tenant_calibration_real"] = len(df_tenant_cal)
    metrics["n_tenant_train_students"] = int(df_tenant_train["__group_id"].nunique())
    metrics["n_tenant_calibration_students"] = int(df_tenant_cal["__group_id"].nunique())
    metrics["n_tenant_test_students"] = int(df_tenant_test["__group_id"].nunique())
    metrics["n_temporally_excluded_events"] = int(
        len(df_tenant) - len(df_tenant_train) - len(df_tenant_cal) - len(df_tenant_test)
    )

    try:
        base_model = load_model()
        try:
            base_calibrator = load_calibrator()
            base_prob = base_calibrator.predict_proba(df_tenant_test[FEATURE_COLUMNS])[:, 1]
        except Exception:
            base_prob = base_model.predict_proba(df_tenant_test[FEATURE_COLUMNS])[:, 1]
        metrics["baseline_auc_same_test"] = float(roc_auc_score(df_tenant_test["label"], base_prob))
        metrics["baseline_average_precision_same_test"] = float(
            average_precision_score(df_tenant_test["label"], base_prob)
        )
    except Exception:
        metrics["baseline_auc_same_test"] = None
        metrics["baseline_average_precision_same_test"] = None

    tenant_dir = MODELS_DIR / "tenants" / _safe_tenant_dirname(tenant.slug)
    tenant_dir.mkdir(parents=True, exist_ok=True)
    version = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    model_path = tenant_dir / f"model_{version}.joblib"
    cal_path = tenant_dir / f"calibrator_{version}.joblib"
    joblib.dump(model, model_path)
    if calibrator is not None:
        joblib.dump(calibrator, cal_path)
    metrics["artifact_sha256"] = hashlib.sha256(model_path.read_bytes()).hexdigest()
    (tenant_dir / f"meta_{version}.json").write_text(json.dumps({**metrics, "feature_columns": FEATURE_COLUMNS, "version": version}, indent=2), encoding="utf-8")

    base_auc = metrics.get("baseline_auc_same_test")

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
        "model_scope": "tenant", "training_data": metrics.get("training_data"),
        "metrics": {k: metrics.get(k) for k in [
            "auc", "average_precision", "brier_score", "accuracy", "n_tenant_events",
            "n_tenant_positive", "n_train", "n_calibration", "n_test",
            "n_tenant_train_real_events", "n_tenant_calibration_real_events",
            "n_tenant_test_real_events", "n_synthetic_training_rows",
            "n_repeated_tenant_training_rows", "temporal_train_ratio",
            "temporal_calibration_ratio", "temporal_test_ratio", "n_temporal_evaluation_events",
            "n_tenant_train_students", "n_tenant_calibration_students", "n_tenant_test_students",
            "n_temporally_excluded_events", "train_period_end", "calibration_period_start",
            "train_label_observation_end", "calibration_period_end",
            "calibration_label_observation_end", "test_period_start", "test_label_observation_end",
            "evaluation_split", "calibration_method", "target_definition",
            "baseline_auc_same_test", "baseline_average_precision_same_test",
            "blended", "top_features", "disclaimer",
        ]},
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


def load_tenant_model_from_path(storage_path: str, slug: str, expected_sha256: str | None = None):
    global _tenant_model_cache
    if slug in _tenant_model_cache:
        return _tenant_model_cache[slug]
    path = get_model_storage().resolve(storage_path)
    if not path.exists():
        return None
    if expected_sha256:
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if not hmac.compare_digest(actual, expected_sha256):
            raise ValueError(
                f"Integridade do artefato de modelo falhou para tenant '{slug}' (checksum nao confere)."
            )
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
        if art and art.storage_path and (art.metrics or {}).get("target_definition") == TARGET_DEFINITION_VERSION:
            expected_sha256 = (art.metrics or {}).get("artifact_sha256")
            model = load_tenant_model_from_path(art.storage_path, tenant.slug, expected_sha256=expected_sha256)
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
