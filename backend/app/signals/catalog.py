"""Catálogo versionado de sinais autorizados (Wave 1.1).

Definições são estáticas em código. Avaliação individual vive em evaluate.py.
"""
from __future__ import annotations

from typing import Any, Literal

ReliabilityClass = Literal["available", "partial", "proxy", "unavailable"]
SignalCategory = Literal["risk", "financial", "engagement", "academic", "relationship"]

# Limiares de ativação documentados nas regras dos sinais (não alteram scoring).
FINANCIAL_DELAY_DAYS_THRESHOLD = 15
DAYS_WITHOUT_LOGIN_THRESHOLD = 21
RISK_INCREASE_SCORE_DELTA = 10.0

SIGNAL_CATALOG: dict[str, dict[str, Any]] = {
    "risk_critical": {
        "id": "risk_critical",
        "name": "Risco crítico",
        "category": "risk",
        "description": (
            "Aluno com nível de risco crítico atribuído pelo motor preditivo "
            "já executado (não recalcula score)."
        ),
        "reliability_class": "available",
        "activation_rule": "risk_level == 'critico' AND risk_score is finite in [0, 100]",
        "data_source": "students.risk_level, students.risk_score",
        "version": "1.0.0",
        "limitations": [
            "Depende de scoring prévio; ausência de score não ativa este sinal.",
            "Não interpreta NULL como risco baixo.",
        ],
    },
    "risk_medium": {
        "id": "risk_medium",
        "name": "Risco médio",
        "category": "risk",
        "description": "Aluno com nível de risco médio atribuído pelo motor preditivo.",
        "reliability_class": "available",
        "activation_rule": "risk_level == 'medio' AND risk_score is finite in [0, 100]",
        "data_source": "students.risk_level, students.risk_score",
        "version": "1.0.0",
        "limitations": [
            "Depende de scoring prévio.",
            "Não combina automaticamente com outros sinais nesta versão.",
        ],
    },
    "missing_score": {
        "id": "missing_score",
        "name": "Ausência de score",
        "category": "risk",
        "description": (
            "Meta-sinal de cobertura: aluno ativo sem avaliação de risco utilizável. "
            "Não indica baixo risco."
        ),
        "reliability_class": "available",
        "activation_rule": (
            "risk_score is NULL OR risk_level not in {baixo, medio, critico} "
            "OR risk_score not finite in [0, 100]"
        ),
        "data_source": "students.risk_level, students.risk_score",
        "version": "1.0.0",
        "limitations": [
            "Sinal de lacuna de dados, não de risco comportamental.",
            "Mutuamente exclusivo com risk_critical e risk_medium quando o score é válido.",
        ],
    },
    "financial_delay": {
        "id": "financial_delay",
        "name": "Atraso financeiro",
        "category": "financial",
        "description": (
            f"Dias de atraso de boleto acima de {FINANCIAL_DELAY_DAYS_THRESHOLD} "
            "quando o campo está presente e numérico."
        ),
        "reliability_class": "partial",
        "activation_rule": (
            f"dias_atraso_boleto is not NULL AND dias_atraso_boleto >= {FINANCIAL_DELAY_DAYS_THRESHOLD}"
        ),
        "data_source": "students.dias_atraso_boleto (snapshot de importação)",
        "version": "1.0.0",
        "limitations": [
            "Snapshot de importação; não é ledger de parcelas.",
            "NULL significa dado insuficiente, não ausência de atraso.",
        ],
    },
    "days_without_login_elevated": {
        "id": "days_without_login_elevated",
        "name": "Dias sem login elevados",
        "category": "engagement",
        "description": (
            f"dias_sem_login >= {DAYS_WITHOUT_LOGIN_THRESHOLD} quando o campo está presente."
        ),
        "reliability_class": "partial",
        "activation_rule": (
            f"dias_sem_login is not NULL AND dias_sem_login >= {DAYS_WITHOUT_LOGIN_THRESHOLD}"
        ),
        "data_source": "students.dias_sem_login (snapshot de importação)",
        "version": "1.0.0",
        "limitations": [
            "Não é telemetria LMS em tempo real.",
            "NULL não ativa o sinal.",
        ],
    },
    "risk_increase": {
        "id": "risk_increase",
        "name": "Aumento relevante de risco",
        "category": "risk",
        "description": (
            f"Comparação entre as duas avaliações históricas mais recentes com o mesmo "
            f"model_version e score_semantics_version; delta de score >= {RISK_INCREASE_SCORE_DELTA} "
            "ou elevação de nível (baixo→medio/critico, medio→critico)."
        ),
        "reliability_class": "partial",
        "activation_rule": (
            "two comparable risk_assessments; score delta or level upgrade; "
            "same model_version and score_semantics_version"
        ),
        "data_source": "risk_assessments (tenant-scoped history)",
        "version": "1.0.0",
        "limitations": [
            "Exige pelo menos duas avaliações comparáveis.",
            "Mudança de model_version ou score_semantics_version não conta como aumento.",
            "Schema incompleto de risk_assessments implica insufficient_data.",
        ],
    },
}


def list_catalog() -> list[dict[str, Any]]:
    return [dict(SIGNAL_CATALOG[sid]) for sid in sorted(SIGNAL_CATALOG.keys())]


def get_signal_definition(signal_id: str) -> dict[str, Any] | None:
    item = SIGNAL_CATALOG.get(signal_id)
    return dict(item) if item else None
