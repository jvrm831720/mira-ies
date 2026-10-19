"""
Feature Engineering para o Motor de Risco de Evasão.

Alinhado com o documento do MVP:
- Engajamento Digital (AVA/LMS)
- Desempenho Acadêmico
- Comportamento Financeiro
- Histórico Cadastral (semestre, forma de ingresso)
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
]

FEATURE_LABELS_PT = {
    "dias_atraso_boleto": "Dias de atraso no boleto",
    "recorrencia_atrasos": "Recorrência de atrasos financeiros",
    "dias_sem_login": "Dias sem acesso ao AVA/LMS",
    "presenca_percentual": "Percentual de presença",
    "nota_media": "Nota média",
    "reprovacoes": "Quantidade de reprovações",
    "semestre": "Semestre atual",
    "is_early_semester": "Está no 1º ou 2º semestre",
    "atraso_grave": "Atraso financeiro grave (>15 dias)",
    "engajamento_critico": "Engajamento crítico (>14 dias sem login)",
    "desempenho_baixo": "Desempenho acadêmico baixo (nota < 6)",
    "presenca_baixa": "Presença baixa (<70%)",
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
            val = student.get(key, default)
        else:
            val = getattr(student, key, default)
        return val

    dias_atraso = _safe_int(get("dias_atraso_boleto"), FEATURE_DEFAULTS["dias_atraso_boleto"])
    recorrencia = _safe_int(get("recorrencia_atrasos"), FEATURE_DEFAULTS["recorrencia_atrasos"])
    dias_login = _safe_int(get("dias_sem_login"), FEATURE_DEFAULTS["dias_sem_login"])
    presenca = _safe_float(get("presenca_percentual"), FEATURE_DEFAULTS["presenca_percentual"])
    nota = _safe_float(get("nota_media"), FEATURE_DEFAULTS["nota_media"])
    reprovacoes = _safe_int(get("reprovacoes"), FEATURE_DEFAULTS["reprovacoes"])
    semestre = _safe_int(get("semestre"), FEATURE_DEFAULTS["semestre"])

    presenca = max(0.0, min(100.0, presenca))
    nota = max(0.0, min(10.0, nota))
    dias_atraso = max(0, dias_atraso)
    dias_login = max(0, dias_login)

    return {
        "dias_atraso_boleto": float(dias_atraso),
        "recorrencia_atrasos": float(recorrencia),
        "dias_sem_login": float(dias_login),
        "presenca_percentual": float(presenca),
        "nota_media": float(nota),
        "reprovacoes": float(reprovacoes),
        "semestre": float(semestre),
        "is_early_semester": 1.0 if semestre <= 2 else 0.0,
        "atraso_grave": 1.0 if dias_atraso > 15 else 0.0,
        "engajamento_critico": 1.0 if dias_login > 14 else 0.0,
        "desempenho_baixo": 1.0 if nota < 6.0 else 0.0,
        "presenca_baixa": 1.0 if presenca < 70.0 else 0.0,
    }


def features_to_dataframe(features_list: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(features_list)
    for col in FEATURE_COLUMNS:
        if col not in df.columns:
            df[col] = 0.0
    return df[FEATURE_COLUMNS]


def students_to_feature_matrix(students: list[Any]) -> tuple[pd.DataFrame, list[dict]]:
    feature_dicts = [build_features_from_student(s) for s in students]
    df = features_to_dataframe(feature_dicts)
    return df, feature_dicts


def missing_feature_flags(student: dict | Any) -> list[str]:
    important = [
        "dias_atraso_boleto",
        "dias_sem_login",
        "presenca_percentual",
        "nota_media",
        "semestre",
    ]
    missing = []
    for key in important:
        if isinstance(student, dict):
            val = student.get(key)
        else:
            val = getattr(student, key, None)
        if val is None:
            missing.append(key)
    return missing
