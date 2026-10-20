"""Testes das regras de negocio de risco."""
from app.ml.rules import apply_business_rules


def test_critical_delay_boosts_score():
    features = {
        "dias_atraso_boleto": 60,
        "recorrencia_atrasos": 3,
        "dias_sem_login": 5,
        "presenca_percentual": 90.0,
        "nota_media": 7.0,
        "reprovacoes": 0,
        "semestre": 3,
    }
    result = apply_business_rules(features, model_score=40.0)
    assert result["adjusted_score"] >= 40.0
    assert result["rule_boost"] > 0 or len(result["rule_flags"]) > 0


def test_healthy_student_stays_low():
    features = {
        "dias_atraso_boleto": 0,
        "recorrencia_atrasos": 0,
        "dias_sem_login": 1,
        "presenca_percentual": 98.0,
        "nota_media": 8.5,
        "reprovacoes": 0,
        "semestre": 2,
    }
    result = apply_business_rules(features, model_score=15.0)
    assert result["adjusted_score"] <= 40
    assert result["risk_level"] in ("baixo", "medio")
