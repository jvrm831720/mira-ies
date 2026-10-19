"""
Explicabilidade via SHAP (Explainable AI).
Top 3 fatores em linguagem compreensivel para a coordenacao.
"""

from __future__ import annotations

from typing import Any
import numpy as np
import pandas as pd
import shap

from app.ml.features import FEATURE_COLUMNS, FEATURE_LABELS_PT
from app.ml.model import load_model

_explainer: shap.TreeExplainer | None = None


def get_explainer() -> shap.TreeExplainer:
    global _explainer
    if _explainer is None:
        model = load_model()
        _explainer = shap.TreeExplainer(model)
    return _explainer


def explain_instance(
    features: dict[str, float] | pd.Series | pd.DataFrame,
    top_k: int = 3,
) -> list[dict[str, Any]]:
    explainer = get_explainer()
    if isinstance(features, dict):
        X = pd.DataFrame([features])[FEATURE_COLUMNS]
    elif isinstance(features, pd.Series):
        X = pd.DataFrame([features])[FEATURE_COLUMNS]
    else:
        X = features[FEATURE_COLUMNS]

    shap_values = explainer.shap_values(X)
    if isinstance(shap_values, list):
        sv = shap_values[1][0] if len(shap_values) > 1 else shap_values[0][0]
    else:
        arr = np.asarray(shap_values)
        if arr.ndim == 3:
            sv = arr[0, :, 1] if arr.shape[-1] > 1 else arr[0, :, 0]
        elif arr.ndim == 2:
            sv = arr[0]
        else:
            sv = arr

    sv = np.asarray(sv).flatten()
    if len(sv) != len(FEATURE_COLUMNS):
        sv = np.zeros(len(FEATURE_COLUMNS))

    abs_sv = np.abs(sv)
    total_abs = abs_sv.sum() + 1e-9
    order = np.argsort(-abs_sv)

    results = []
    for idx in order[:top_k]:
        feat = FEATURE_COLUMNS[idx]
        shap_val = float(sv[idx])
        raw_value = float(X.iloc[0][feat])
        results.append({
            "feature": feat,
            "label": FEATURE_LABELS_PT.get(feat, feat),
            "value": raw_value,
            "shap_value": round(shap_val, 4),
            "contribution": "aumenta_risco" if shap_val > 0 else "reduz_risco",
            "impact_pct": round(float(abs_sv[idx] / total_abs * 100), 1),
        })
    return results


def format_top_factors_human(top_factors: list[dict]) -> str:
    parts = []
    for i, f in enumerate(top_factors, 1):
        label = f["label"]
        value = f["value"]
        if f["feature"] == "dias_atraso_boleto":
            parts.append(f"{i}o Atraso de {int(value)} dias no boleto")
        elif f["feature"] == "dias_sem_login":
            parts.append(f"{i}o {int(value)} dias sem acesso ao AVA")
        elif f["feature"] == "nota_media":
            parts.append(f"{i}o Nota media {value:.1f}")
        elif f["feature"] == "presenca_percentual":
            parts.append(f"{i}o Presenca de {value:.0f}%")
        elif f["feature"] == "reprovacoes":
            parts.append(f"{i}o {int(value)} reprovacao(oes)")
        elif f["feature"] in ("risco_financeiro", "risco_engajamento", "risco_academico"):
            parts.append(f"{i}o {label}")
        elif f["feature"] == "combo_critico" and value >= 1:
            parts.append(f"{i}o Atraso grave combinado com engajamento critico")
        elif f["feature"] == "pressao_inicial" and value >= 1:
            parts.append(f"{i}o Pressao de risco no inicio do curso")
        else:
            parts.append(f"{i}o {label}: {value}")
    return " + ".join(parts)
