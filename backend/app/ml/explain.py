"""
Explicabilidade SHAP vinculada ao estimador que produziu a previsão.
As contribuições explicam a saída bruta do estimador, não a calibração,
as regras de negócio ou ajustes dinâmicos aplicados depois.
"""
from __future__ import annotations

from typing import Any
import numpy as np
import pandas as pd
import shap

from app.ml.features import FEATURE_COLUMNS, FEATURE_LABELS_PT

_explainer_cache: dict[int, tuple[Any, shap.TreeExplainer]] = {}


def get_explainer(model: Any) -> shap.TreeExplainer:
    """Cacheia o explainer pela identidade do estimador, nunca por um modelo global implícito."""
    key = id(model)
    cached = _explainer_cache.get(key)
    if cached is not None and cached[0] is model:
        return cached[1]
    explainer = shap.TreeExplainer(model)
    _explainer_cache[key] = (model, explainer)
    return explainer


def explain_instance(
    features: dict[str, float] | pd.Series | pd.DataFrame,
    top_k: int = 3,
    *,
    model: Any,
    model_scope: str,
    model_version: str,
) -> list[dict[str, Any]]:
    if model is None:
        raise ValueError("O estimador usado no scoring é obrigatório para gerar SHAP.")
    if isinstance(features, dict):
        X = pd.DataFrame([features])[FEATURE_COLUMNS]
    elif isinstance(features, pd.Series):
        X = pd.DataFrame([features])[FEATURE_COLUMNS]
    else:
        X = features[FEATURE_COLUMNS]

    explainer = get_explainer(model)
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
        raise ValueError(
            f"SHAP retornou {len(sv)} contribuições para {len(FEATURE_COLUMNS)} features."
        )

    abs_sv = np.abs(sv)
    total_abs = float(abs_sv.sum())
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
            "shap_value": round(shap_val, 6),
            "contribution": (
                "aumenta_saida_modelo" if shap_val > 0
                else "reduz_saida_modelo" if shap_val < 0
                else "neutra"
            ),
            # Participação relativa na magnitude SHAP deste caso; não é percentual do score.
            "impact_pct": round(float(abs_sv[idx] / total_abs * 100), 1) if total_abs else 0.0,
            "model_scope": model_scope,
            "model_version": str(model_version),
        })
    return results


def format_top_factors_human(top_factors: list[dict]) -> str:
    parts = []
    for i, factor in enumerate(top_factors, 1):
        label = factor["label"]
        value = factor["value"]
        if factor["feature"] == "dias_atraso_boleto":
            parts.append(f"{i}º Atraso de {int(value)} dias no boleto")
        elif factor["feature"] == "dias_sem_login":
            parts.append(f"{i}º {int(value)} dias sem acesso ao AVA")
        elif factor["feature"] == "nota_media":
            parts.append(f"{i}º Nota média {value:.1f}")
        elif factor["feature"] == "presenca_percentual":
            parts.append(f"{i}º Presença de {value:.0f}%")
        elif factor["feature"] == "reprovacoes":
            parts.append(f"{i}º {int(value)} reprovação(ões)")
        elif factor["feature"] in ("risco_financeiro", "risco_engajamento", "risco_academico"):
            parts.append(f"{i}º {label}")
        elif factor["feature"] == "combo_critico" and value >= 1:
            parts.append(f"{i}º Atraso grave combinado com engajamento crítico")
        elif factor["feature"] == "pressao_inicial" and value >= 1:
            parts.append(f"{i}º Pressão de risco no início do curso")
        else:
            parts.append(f"{i}º {label}: {value}")
    return " + ".join(parts)
