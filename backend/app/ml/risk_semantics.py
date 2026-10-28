"""Shared semantics for displayed risk scores and their classifications."""

RISK_SCORE_SEMANTICS_VERSION = "risk-score-v1"


def classify_risk_score(score: float) -> str:
    """Classify the displayed 0–100 score; higher scores mean higher risk."""
    if score >= 70:
        return "critico"
    if score >= 40:
        return "medio"
    return "baixo"
