"""
Treinamento, calibracao e carregamento do modelo de risco.
XGBoost + calibracao isotonica → Risk Score 0-100.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    roc_auc_score,
    average_precision_score,
    brier_score_loss,
    classification_report,
    confusion_matrix,
)
from sklearn.calibration import CalibratedClassifierCV
import xgboost as xgb
import joblib

from app.ml.features import FEATURE_COLUMNS, FEATURE_LABELS_PT

MODELS_DIR = Path(__file__).resolve().parents[2] / "models" / "trained"
MODELS_DIR.mkdir(parents=True, exist_ok=True)

MODEL_PATH = MODELS_DIR / "risk_model_xgb.joblib"
CALIBRATOR_PATH = MODELS_DIR / "risk_calibrator.joblib"
META_PATH = MODELS_DIR / "risk_model_meta.json"
MODEL_VERSION = "0.3.2"

_model_cache: xgb.XGBClassifier | None = None
_calibrator_cache: Any = None


def _generate_synthetic_training_data(n_samples: int = 5000, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    n_low = int(n_samples * 0.40)
    n_mid = int(n_samples * 0.35)
    n_high = n_samples - n_low - n_mid

    def profile(n, atraso, login, presenca, nota, reprov, semestre):
        return pd.DataFrame({
            "dias_atraso_boleto": rng.integers(*atraso, size=n),
            "recorrencia_atrasos": rng.integers(0, 3 if atraso[1] < 20 else 6, size=n),
            "dias_sem_login": rng.integers(*login, size=n),
            "presenca_percentual": rng.uniform(*presenca, size=n).round(1),
            "nota_media": rng.uniform(*nota, size=n).round(1),
            "reprovacoes": rng.integers(*reprov, size=n),
            "semestre": rng.integers(*semestre, size=n),
        })

    low = profile(n_low, (0, 8), (0, 5), (80, 100), (7.0, 10.0), (0, 1), (1, 9))
    mid = profile(n_mid, (5, 25), (5, 20), (55, 85), (5.0, 7.5), (0, 2), (1, 7))
    high = profile(n_high, (15, 60), (14, 45), (30, 65), (2.0, 6.0), (0, 4), (1, 5))
    n_swap = int(n_high * 0.55)
    if n_swap > 0:
        high.loc[high.sample(n=n_swap, random_state=seed).index, "semestre"] = rng.integers(1, 3, size=n_swap)

    df = pd.concat([low, mid, high], ignore_index=True).sample(frac=1.0, random_state=seed).reset_index(drop=True)

    df["is_early_semester"] = (df["semestre"] <= 2).astype(float)
    df["atraso_grave"] = (df["dias_atraso_boleto"] > 15).astype(float)
    df["engajamento_critico"] = (df["dias_sem_login"] > 14).astype(float)
    df["desempenho_baixo"] = (df["nota_media"] < 6.0).astype(float)
    df["presenca_baixa"] = (df["presenca_percentual"] < 70.0).astype(float)
    df["risco_financeiro"] = np.minimum(1.0, (df["dias_atraso_boleto"] / 60.0) * (1.0 + df["recorrencia_atrasos"] / 3.0) / 2.0)
    df["risco_engajamento"] = np.minimum(1.0, (df["dias_sem_login"] / 45.0) * (1.0 - df["presenca_percentual"] / 100.0) * 2.0)
    df["risco_academico"] = np.minimum(1.0, ((10.0 - df["nota_media"]) / 10.0) * (1.0 + df["reprovacoes"] / 2.0) / 2.0)
    df["combo_critico"] = ((df["atraso_grave"] == 1) & (df["engajamento_critico"] == 1)).astype(float)
    df["pressao_inicial"] = df["is_early_semester"] * np.maximum.reduce([df["atraso_grave"], df["engajamento_critico"], df["desempenho_baixo"]])

    linear = (
        0.30 * (df["dias_atraso_boleto"] / 60)
        + 0.15 * (df["recorrencia_atrasos"] / 5)
        + 0.22 * (df["dias_sem_login"] / 45)
        + 0.12 * ((100 - df["presenca_percentual"]) / 100)
        + 0.18 * ((10 - df["nota_media"]) / 10)
        + 0.12 * (df["reprovacoes"] / 3)
        + 0.10 * df["is_early_semester"]
        + 0.12 * df["atraso_grave"]
        + 0.12 * df["engajamento_critico"]
        + 0.10 * df["combo_critico"]
        + 0.08 * df["risco_financeiro"]
        + 0.08 * df["risco_engajamento"]
        + 0.08 * df["risco_academico"]
    )
    noise = rng.normal(0, 0.07, len(df))
    prob = 1 / (1 + np.exp(-(linear * 5 - 2.2 + noise)))
    df["risco_alto"] = (prob > 0.42).astype(int)
    return df


def _split_train_calibration_test(
    X: pd.DataFrame, y: pd.Series, test_size: float = 0.2,
    calibration_size: float = 0.2, seed: int = 42,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Retorna índices disjuntos para treino, calibração e teste final."""
    if test_size <= 0 or calibration_size <= 0 or test_size + calibration_size >= 1:
        raise ValueError("test_size e calibration_size devem ser positivos e somar menos que 1")
    indices = np.arange(len(y))
    train_cal_idx, test_idx = train_test_split(
        indices, test_size=test_size, random_state=seed, stratify=y
    )
    cal_fraction_of_pool = calibration_size / (1 - test_size)
    train_idx, calibration_idx = train_test_split(
        train_cal_idx,
        test_size=cal_fraction_of_pool,
        random_state=seed,
        stratify=y.iloc[train_cal_idx],
    )
    return train_idx, calibration_idx, test_idx


def train_model(n_samples: int = 5000, test_size: float = 0.2, seed: int = 42) -> dict[str, Any]:
    global _model_cache, _calibrator_cache
    df = _generate_synthetic_training_data(n_samples=n_samples, seed=seed)
    X, y = df[FEATURE_COLUMNS], df["risco_alto"]
    train_idx, calibration_idx, test_idx = _split_train_calibration_test(
        X, y, test_size=test_size, calibration_size=0.2, seed=seed
    )
    X_train, y_train = X.iloc[train_idx], y.iloc[train_idx]
    X_cal, y_cal = X.iloc[calibration_idx], y.iloc[calibration_idx]
    X_test, y_test = X.iloc[test_idx], y.iloc[test_idx]

    model = xgb.XGBClassifier(
        n_estimators=200, max_depth=5, learning_rate=0.06, subsample=0.85,
        colsample_bytree=0.8, reg_lambda=1.2, reg_alpha=0.3, min_child_weight=4,
        gamma=0.1, objective="binary:logistic", eval_metric="logloss",
        random_state=seed, n_jobs=-1,
    )
    model.fit(X_train, y_train, verbose=False)

    calibrator = CalibratedClassifierCV(model, method="isotonic", cv="prefit")
    calibrator.fit(X_cal, y_cal)

    y_prob = calibrator.predict_proba(X_test)[:, 1]
    y_pred = (y_prob >= 0.5).astype(int)
    auc = float(roc_auc_score(y_test, y_prob))
    ap = float(average_precision_score(y_test, y_prob))
    brier = float(brier_score_loss(y_test, y_prob))
    report = classification_report(y_test, y_pred, output_dict=True)
    cm = confusion_matrix(y_test, y_pred).tolist()

    importance = model.feature_importances_
    feat_imp = sorted([
        {"feature": f, "label": FEATURE_LABELS_PT.get(f, f), "importance": round(float(i), 4)}
        for f, i in zip(FEATURE_COLUMNS, importance)
    ], key=lambda x: -x["importance"])

    joblib.dump(model, MODEL_PATH)
    joblib.dump(calibrator, CALIBRATOR_PATH)
    meta = {
        "feature_columns": FEATURE_COLUMNS,
        "feature_labels_pt": FEATURE_LABELS_PT,
        "auc": auc,
        "average_precision": ap,
        "brier_score": brier,
        "n_samples": n_samples,
        "n_train": int(len(train_idx)),
        "n_calibration": int(len(calibration_idx)),
        "n_test": int(len(test_idx)),
        "evaluation_split": "stratified_three_way_holdout",
        "calibration_method": "isotonic",
        "validation_disclaimer": (
            "Métricas calculadas em dados sintéticos derivados de uma regra de risco; "
            "não representam validação em dados reais de uma IES."
        ),
        "positive_rate": float(y.mean()),
        "model_type": "XGBClassifier+IsotonicCalibration",
        "version": MODEL_VERSION,
        "n_features": len(FEATURE_COLUMNS),
        "trained_at": pd.Timestamp.utcnow().isoformat(),
        "feature_importance": feat_imp[:10],
        "confusion_matrix": cm,
        "classification_report": {
            "precision_risco_alto": report["1"]["precision"],
            "recall_risco_alto": report["1"]["recall"],
            "f1_risco_alto": report["1"]["f1-score"],
            "accuracy": report["accuracy"],
        },
    }
    META_PATH.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    _model_cache, _calibrator_cache = model, calibrator
    return {
        "auc": round(auc, 4),
        "average_precision": round(ap, 4),
        "brier_score": round(brier, 4),
        "accuracy": round(report["accuracy"], 4),
        "precision_risco_alto": round(report["1"]["precision"], 4),
        "recall_risco_alto": round(report["1"]["recall"], 4),
        "f1_risco_alto": round(report["1"]["f1-score"], 4),
        "n_features": len(FEATURE_COLUMNS),
        "n_samples": n_samples,
        "version": MODEL_VERSION,
        "top_features": feat_imp[:5],
        "n_train": int(len(train_idx)),
        "n_calibration": int(len(calibration_idx)),
        "n_test": int(len(test_idx)),
        "evaluation_split": "stratified_three_way_holdout",
        "validation_disclaimer": meta["validation_disclaimer"],
    }


def load_model() -> xgb.XGBClassifier:
    global _model_cache
    if _model_cache is not None:
        return _model_cache
    if not MODEL_PATH.exists():
        train_model()
    _model_cache = joblib.load(MODEL_PATH)
    return _model_cache


def load_calibrator():
    global _calibrator_cache
    if _calibrator_cache is not None:
        return _calibrator_cache
    if not CALIBRATOR_PATH.exists():
        train_model()
    _calibrator_cache = joblib.load(CALIBRATOR_PATH)
    return _calibrator_cache


def load_meta() -> dict:
    if not META_PATH.exists():
        train_model()
    return json.loads(META_PATH.read_text(encoding="utf-8"))


def predict_proba(model: xgb.XGBClassifier, X: pd.DataFrame, calibrated: bool = True) -> np.ndarray:
    X = X[FEATURE_COLUMNS]
    if calibrated:
        try:
            return load_calibrator().predict_proba(X)[:, 1]
        except Exception:
            pass
    return model.predict_proba(X)[:, 1]


def probability_to_risk_score(proba: float) -> float:
    return round(float(np.clip(proba * 100, 0, 100)), 1)


def risk_level_from_score(score: float) -> str:
    if score >= 70:
        return "critico"
    if score >= 40:
        return "medio"
    return "baixo"


def invalidate_cache():
    global _model_cache, _calibrator_cache
    _model_cache = None
    _calibrator_cache = None
