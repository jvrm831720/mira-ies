"""
Treinamento, serialização e carregamento do modelo de risco.
Usa XGBoost (classificação binária: risco alto vs baixo) e mapeia para score 0-100.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score, classification_report
import xgboost as xgb
import joblib

from app.ml.features import FEATURE_COLUMNS, FEATURE_LABELS_PT, build_features_from_student, features_to_dataframe

MODELS_DIR = Path(__file__).resolve().parents[2] / "models" / "trained"
MODELS_DIR.mkdir(parents=True, exist_ok=True)

MODEL_PATH = MODELS_DIR / "risk_model_xgb.joblib"
META_PATH = MODELS_DIR / "risk_model_meta.json"


def _generate_synthetic_training_data(n_samples: int = 4000, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    data = {
        "dias_atraso_boleto": rng.integers(0, 60, n_samples),
        "recorrencia_atrasos": rng.integers(0, 6, n_samples),
        "dias_sem_login": rng.integers(0, 45, n_samples),
        "presenca_percentual": rng.uniform(30, 100, n_samples).round(1),
        "nota_media": rng.uniform(2.0, 10.0, n_samples).round(1),
        "reprovacoes": rng.integers(0, 4, n_samples),
        "semestre": rng.integers(1, 9, n_samples),
    }
    df = pd.DataFrame(data)
    df["is_early_semester"] = (df["semestre"] <= 2).astype(float)
    df["atraso_grave"] = (df["dias_atraso_boleto"] > 15).astype(float)
    df["engajamento_critico"] = (df["dias_sem_login"] > 14).astype(float)
    df["desempenho_baixo"] = (df["nota_media"] < 6.0).astype(float)
    df["presenca_baixa"] = (df["presenca_percentual"] < 70.0).astype(float)

    linear = (
        0.35 * (df["dias_atraso_boleto"] / 60)
        + 0.20 * (df["recorrencia_atrasos"] / 5)
        + 0.25 * (df["dias_sem_login"] / 45)
        + 0.15 * ((100 - df["presenca_percentual"]) / 100)
        + 0.20 * ((10 - df["nota_media"]) / 10)
        + 0.15 * (df["reprovacoes"] / 3)
        + 0.10 * df["is_early_semester"]
        + 0.10 * df["atraso_grave"]
        + 0.10 * df["engajamento_critico"]
    )
    noise = rng.normal(0, 0.08, n_samples)
    prob = 1 / (1 + np.exp(-(linear * 4 - 2 + noise)))
    df["risco_alto"] = (prob > 0.45).astype(int)
    return df


def train_model(n_samples: int = 4000, test_size: float = 0.2, seed: int = 42) -> dict[str, Any]:
    df = _generate_synthetic_training_data(n_samples=n_samples, seed=seed)
    X = df[FEATURE_COLUMNS]
    y = df["risco_alto"]
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=seed, stratify=y
    )
    model = xgb.XGBClassifier(
        n_estimators=120, max_depth=5, learning_rate=0.08,
        subsample=0.85, colsample_bytree=0.85, reg_lambda=1.0,
        min_child_weight=3, objective="binary:logistic",
        eval_metric="logloss", random_state=seed, n_jobs=-1,
    )
    model.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)
    y_prob = model.predict_proba(X_test)[:, 1]
    y_pred = (y_prob >= 0.5).astype(int)
    auc = float(roc_auc_score(y_test, y_prob))
    report = classification_report(y_test, y_pred, output_dict=True)
    joblib.dump(model, MODEL_PATH)
    meta = {
        "feature_columns": FEATURE_COLUMNS,
        "feature_labels_pt": FEATURE_LABELS_PT,
        "auc": auc,
        "n_samples": n_samples,
        "positive_rate": float(y.mean()),
        "model_type": "XGBClassifier",
        "version": "0.2.0",
        "trained_at": pd.Timestamp.utcnow().isoformat(),
    }
    META_PATH.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return {
        "auc": auc,
        "accuracy": report["accuracy"],
        "precision_risco_alto": report["1"]["precision"],
        "recall_risco_alto": report["1"]["recall"],
        "f1_risco_alto": report["1"]["f1-score"],
        "model_path": str(MODEL_PATH),
        "n_features": len(FEATURE_COLUMNS),
    }


def load_model() -> xgb.XGBClassifier:
    if not MODEL_PATH.exists():
        print("Modelo nao encontrado. Treinando modelo inicial...")
        train_model()
    return joblib.load(MODEL_PATH)


def load_meta() -> dict:
    if not META_PATH.exists():
        train_model()
    return json.loads(META_PATH.read_text(encoding="utf-8"))


def predict_proba(model: xgb.XGBClassifier, X: pd.DataFrame) -> np.ndarray:
    X = X[FEATURE_COLUMNS]
    return model.predict_proba(X)[:, 1]


def probability_to_risk_score(proba: float) -> float:
    score = proba * 100
    return round(float(np.clip(score, 0, 100)), 1)


def risk_level_from_score(score: float) -> str:
    if score >= 70:
        return "critico"
    if score >= 40:
        return "medio"
    return "baixo"
