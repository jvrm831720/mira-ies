"""
Feature Engineering para o Motor de Risco de Evasão.

17 features derivadas de 7 campos de origem. Ausência e valores inválidos
são bloqueados pelo contrato de qualidade; nunca recebem defaults favoráveis.
"""
from __future__ import annotations

from typing import Any
import numpy as np
import pandas as pd

from app.ml.data_quality import assess_student_data_quality, require_scoreable_student

FEATURE_COLUMNS = [
    "dias_atraso_boleto", "recorrencia_atrasos", "dias_sem_login",
    "presenca_percentual", "nota_media", "reprovacoes", "semestre",
    "is_early_semester", "atraso_grave", "engajamento_critico",
    "desempenho_baixo", "presenca_baixa", "risco_financeiro",
    "risco_engajamento", "risco_academico", "combo_critico", "pressao_inicial",
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
    "risco_financeiro": "Pressão financeira combinada",
    "risco_engajamento": "Desengajamento digital combinado",
    "risco_academico": "Dificuldade acadêmica combinada",
    "combo_critico": "Atraso grave + engajamento crítico",
    "pressao_inicial": "Pressão no início do curso",
}


def build_features_from_student(student: dict | Any) -> dict[str, float]:
    require_scoreable_student(student)

    def get(key: str) -> float:
        value = student.get(key) if isinstance(student, dict) else getattr(student, key)
        return float(value)

    dias_atraso = get("dias_atraso_boleto")
    recorrencia = get("recorrencia_atrasos")
    dias_login = get("dias_sem_login")
    presenca = get("presenca_percentual")
    nota = get("nota_media")
    reprovacoes = get("reprovacoes")
    semestre = get("semestre")

    is_early = 1.0 if semestre <= 2 else 0.0
    atraso_grave = 1.0 if dias_atraso > 15 else 0.0
    engajamento_critico = 1.0 if dias_login > 14 else 0.0
    desempenho_baixo = 1.0 if nota < 6.0 else 0.0
    presenca_baixa = 1.0 if presenca < 70.0 else 0.0

    risco_financeiro = min(1.0, (dias_atraso / 60.0) * (1.0 + recorrencia / 3.0) / 2.0)
    risco_engajamento = min(1.0, (dias_login / 45.0) * (1.0 - presenca / 100.0) * 2.0)
    risco_academico = min(1.0, ((10.0 - nota) / 10.0) * (1.0 + reprovacoes / 2.0) / 2.0)
    combo_critico = 1.0 if atraso_grave and engajamento_critico else 0.0
    pressao_inicial = is_early * max(atraso_grave, engajamento_critico, desempenho_baixo)

    return {
        "dias_atraso_boleto": dias_atraso,
        "recorrencia_atrasos": recorrencia,
        "dias_sem_login": dias_login,
        "presenca_percentual": presenca,
        "nota_media": nota,
        "reprovacoes": reprovacoes,
        "semestre": semestre,
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
    missing = [col for col in FEATURE_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(f"Feature matrix incompleta: {', '.join(missing)}")
    df = df[FEATURE_COLUMNS]
    if df.isna().any().any() or not np.isfinite(df.to_numpy(dtype=float)).all():
        raise ValueError("Feature matrix contém valores ausentes ou não finitos.")
    return df


def students_to_feature_matrix(students: list[Any]) -> tuple[pd.DataFrame, list[dict]]:
    feature_dicts = [build_features_from_student(s) for s in students]
    return features_to_dataframe(feature_dicts), feature_dicts


def missing_feature_flags(student: dict | Any) -> list[str]:
    quality = assess_student_data_quality(student)
    return quality["missing_fields"] + quality["invalid_fields"]
