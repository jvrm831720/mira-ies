"""Catálogo estático e versionado dos grupos virtuais da Wave 2.2."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.signals.catalog import SIGNAL_CATALOG

GroupState = Literal["TRUE", "FALSE", "INDETERMINATE"]
GROUP_CATALOG_VERSION = "1.0.0"
OPERATIONAL_SIGNAL_IDS = (
    "risk_critical",
    "risk_medium",
    "financial_delay",
    "days_without_login_elevated",
    "risk_increase",
)


@dataclass(frozen=True)
class StudentGroupDefinition:
    id: str
    name: str
    description: str
    signal_ids: tuple[str, ...]
    limitations: tuple[str, ...]
    coverage_semantics: str


GROUP_DEFINITIONS: tuple[StudentGroupDefinition, ...] = (
    StudentGroupDefinition(
        id="risk_critical",
        name="Risco crítico",
        description="Alunos ativos cujo sinal risk_critical está definitivamente ativo.",
        signal_ids=("risk_critical",),
        limitations=tuple(SIGNAL_CATALOG["risk_critical"]["limitations"]),
        coverage_semantics="INDETERMINATE quando o score ou nível de risco não é utilizável.",
    ),
    StudentGroupDefinition(
        id="risk_medium",
        name="Risco médio",
        description="Alunos ativos cujo sinal risk_medium está definitivamente ativo.",
        signal_ids=("risk_medium",),
        limitations=tuple(SIGNAL_CATALOG["risk_medium"]["limitations"]),
        coverage_semantics="INDETERMINATE quando o score ou nível de risco não é utilizável.",
    ),
    StudentGroupDefinition(
        id="financial_delay",
        name="Atraso financeiro",
        description="Alunos ativos com atraso financeiro igual ou superior ao limiar do sinal.",
        signal_ids=("financial_delay",),
        limitations=tuple(SIGNAL_CATALOG["financial_delay"]["limitations"]),
        coverage_semantics="INDETERMINATE quando o snapshot financeiro é nulo ou inválido.",
    ),
    StudentGroupDefinition(
        id="days_without_login_elevated",
        name="Dias sem login elevados",
        description="Alunos ativos acima do limiar documentado de dias sem login.",
        signal_ids=("days_without_login_elevated",),
        limitations=tuple(SIGNAL_CATALOG["days_without_login_elevated"]["limitations"]),
        coverage_semantics="INDETERMINATE quando o snapshot de login é nulo ou inválido.",
    ),
    StudentGroupDefinition(
        id="risk_increase",
        name="Aumento relevante de risco",
        description="Alunos ativos com aumento relevante em avaliações históricas comparáveis.",
        signal_ids=("risk_increase",),
        limitations=tuple(SIGNAL_CATALOG["risk_increase"]["limitations"]),
        coverage_semantics="INDETERMINATE sem duas avaliações comparáveis ou se o histórico falhar.",
    ),
    StudentGroupDefinition(
        id="multiple_active_signals",
        name="Múltiplos sinais ativos",
        description="Alunos ativos com pelo menos dois dos cinco sinais operacionais definitivamente ativos.",
        signal_ids=OPERATIONAL_SIGNAL_IDS,
        limitations=(
            "Considera somente os cinco sinais operacionais; missing_score é excluído.",
            "Sinais indeterminados não são contados como ativos.",
        ),
        coverage_semantics="INDETERMINATE se sinais indeterminados ainda puderem elevar a contagem para dois.",
    ),
    StudentGroupDefinition(
        id="missing_score",
        name="Sem score",
        description="Alunos ativos sem score de risco utilizável; não representa baixo risco.",
        signal_ids=("missing_score",),
        limitations=tuple(SIGNAL_CATALOG["missing_score"]["limitations"]),
        coverage_semantics="TRUE quando a ausência de score utilizável é identificada.",
    ),
)


def get_group_definition(group_id: str) -> StudentGroupDefinition | None:
    return next((item for item in GROUP_DEFINITIONS if item.id == group_id), None)


def serialize_catalog_item(item: StudentGroupDefinition) -> dict[str, object]:
    return {
        "id": item.id,
        "name": item.name,
        "description": item.description,
        "signal_ids": list(item.signal_ids),
        "limitations": list(item.limitations),
        "coverage_semantics": item.coverage_semantics,
    }
