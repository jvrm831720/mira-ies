"""Inteligência de Sinais — catálogo e avaliação sob demanda."""

from app.signals.catalog import SIGNAL_CATALOG, get_signal_definition, list_catalog
from app.signals.evaluate import evaluate_student_signals, EvaluationResult

__all__ = [
    "SIGNAL_CATALOG",
    "get_signal_definition",
    "list_catalog",
    "evaluate_student_signals",
    "EvaluationResult",
]
