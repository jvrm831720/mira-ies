"""
Feature Engineering para o Motor de Risco de Evasao.

17 features: originais + flags + interacoes.
"""

from __future__ import annotations

from typing import Any
import numpy as np
import pandas as pd

FEATURE_COLUMNS = [
    "dias_atraso_boleto",
    "recorrencia_atrasos",
    "dias_sem_login",
    "presenca_percentual",
    "nota_media",
    "reprovacoes",
    "semestre",
    "is_early_semester",
    "atraso_grave",
    "engajamento_critico",
    "desempenho_baixo",
    "presenca_baixa",
    "risco_financeiro",
    "risco_engajamento",
    "risco_academico",
    "combo_critico",
    "pressao_inicial",
]

FEATURE_LABELS_PT = {
    "dias_atraso_boleto": "Dias de atraso no boleto",
    "recorrencia_atrasos": "Recorrencia de atrasos financeiros",
    "dias_sem_login": "Dias sem acesso ao AVA/LMS",
    "presenca_percentual": "Percentual de presenca",
    "nota_media": "Nota media",
    "reprovacoes": "Quantidade de reprovacoes",
    "semestre": "Semestre atual",
    "is_early_semester": "Esta no 1o ou 2o semestre",
    "atraso_grave": "Atraso financeiro grave (>15 dias)",
    "engajamento_critico": "Engajamento critico (>14 dias sem login)",
    "desempenho_baixo": "Desempenho academico baixo (nota < 6)",
    "presenca_baixa": "Presenca baixa (<70%)",
    "risco_financeiro": "Pressao financeira combinada",
    "risco_engajamento": "Desengajamento digital combinado",
    "risco_academico": "Dificuldade academica combinada",
    "combo_critico": "Atraso grave + engajamento critico",
    "pressao_inicial": "Pressao no inicio do curso",
}

FEATURE_DEFAULTS = {
    "dias_atraso_boleto": 0,
    "recorrencia_atrasos": 0,
    "dias_sem_login": 0,
    "presenca_percentual": 100.0,
    "nota_media": 7.0,
    "reprovacoes": 0,
    "semestre": 3,
}


def _safe_float(v: Any, default: float = 0.0) -> float:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _safe_int(v: Any, default: int = 0) -> int:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return default
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def build_features_from_student(student: dict | Any) -> dict[str, float]:
    def get(key: str, default=None):
        if isinstance(student, dict):
            return student.get(key, default)
        return getattr(student, key, default)

    dias_atraso = max(0, _safe_int(get("dias_atraso_boleto"), FEATURE_DEFAULTS["dias_atraso_boleto"]))
    recorrencia = max(0, _safe_int(get("recorrencia_atrasos"), FEATURE_DEFAULTS["recorrencia_atrasos"]))
    dias_login = max(0, _safe_int(get("dias_sem_login"), FEATURE_DEFAULTS["dias_sem_login"]))
    presenca = max(0.0, min(100.0, _safe_float(get("presenca_percentual"), FEATURE_DEFAULTS["presenca_percentual"])))
    nota = max(0.0, min(10.0, _safe_float(get("nota_media"), FEATURE_DEFAULTS["nota_media"])))
    reprovacoes = max(0, _safe_int(get("reprovacoes"), FEATURE_DEFAULTS["reprovacoes"]))
    semestre = max(1, _safe_int(get("semestre"), FEATURE_DEFAULTS["semestre"]))

    is_early = 1.0 if semestre <= 2 else 0.0
    atraso_grave = 1.0 if dias_atraso > 15 else 0.0
    engajamento_critico = 1.0 if dias_login > 14 else 0.0
    desempenho_baixo = 1.0 if nota < 6.0 else 0.0
    presenca_baixa = 1.0 if presenca < 70.0 else 0.0

    risco_financeiro = min(1.0, (dias_atraso / 60.0) * (1.0 + recorrencia / 3.0) / 2.0)
    risco_engajamento = min(1.0, (dias_login / 45.0) * (1.0 - presenca / 100.0) * 2.0)
    risco_academico = min(1.0, ((10.0 - nota) / 10.0) * (1.0 + reprovacoes / 2.0) / 2.0)
    combo_critico = 1.0 if (atraso_grave and engajamento_critico) else 0.0
    pressao_inicial = is_early * max(atraso_grave, engajamento_critico, desempenho_baixo)

    return {
        "dias_atraso_boleto": float(dias_atraso),
        "recorrencia_atrasos": float(recorrencia),
        "dias_sem_login": float(dias_login),
        "presenca_percentual": float(presenca),
        "nota_media": float(nota),
        "reprovacoes": float(reprovacoes),
        "semestre": float(semestre),
        "is_early_semester": is_early,
        "atraso_grave": atraso_grave,
        "engajamento_critico": engajamento_critico,
        "desempenho_baixo": desempenho_baixo,
        "presenca_baixa": presenca_baixa,
        "risco_financeiro": float(risco_financeiro),
        "risco_engajamento": float(risco_engajamento),
        "risco_academico": float(risco_academico),
        "combo_critico": combo_critico,
        "pressao_inicial": float(pressao_inicial),
    }


def features_to_dataframe(features_list: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(features_list)
    for col in FEATURE_COLUMNS:
        if col not in df.columns:
            df[col] = 0.0
    return df[FEATURE_COLUMNS]


def students_to_feature_matrix(students: list[Any]) -> tuple[pd.DataFrame, list[dict]]:
    feature_dicts = [build_features_from_student(s) for s in students]
    return features_to_dataframe(feature_dicts), feature_dicts


def missing_feature_flags(student: dict | Any) -> list[str]:
    important = ["dias_atraso_boleto", "dias_sem_login", "presenca_percentual", "nota_media", "semestre"]
    missing = []
    for key in important:
        val = student.get(key) if isinstance(student, dict) else getattr(student, key, None)
        if val is None:
            missing.append(key)
    return missing
