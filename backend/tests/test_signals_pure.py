"""Testes puros dos avaliadores de sinais (sem Postgres)."""
from __future__ import annotations

from app.signals.catalog import (
    DAYS_WITHOUT_LOGIN_THRESHOLD,
    FINANCIAL_DELAY_DAYS_THRESHOLD,
    RISK_INCREASE_SCORE_DELTA,
    SIGNAL_CATALOG,
    list_catalog,
)
from app.signals.evaluate import (
    evaluate_days_without_login,
    evaluate_financial_delay,
    evaluate_missing_score,
    evaluate_risk_critical,
    evaluate_risk_increase,
    evaluate_risk_medium,
    evaluate_student_signals,
)

TS = "2026-11-01T12:00:00+00:00"


def test_catalog_has_six_signals():
    cat = list_catalog()
    assert len(cat) == 6
    ids = {c["id"] for c in cat}
    assert ids == set(SIGNAL_CATALOG.keys())
    for item in cat:
        assert item["version"]
        assert item["reliability_class"] in {"available", "partial", "proxy", "unavailable"}
        assert item["limitations"]


def test_risk_critical_active():
    ev = evaluate_risk_critical({"risk_level": "critico", "risk_score": 88.5}, TS)
    assert ev.active is True
    assert ev.insufficient_data is False


def test_risk_critical_null_is_insufficient_not_low_risk():
    ev = evaluate_risk_critical({"risk_level": None, "risk_score": None}, TS)
    assert ev.active is False
    assert ev.insufficient_data is True


def test_risk_medium_and_not_critical():
    st = {"risk_level": "medio", "risk_score": 55}
    assert evaluate_risk_medium(st, TS).active is True
    assert evaluate_risk_critical(st, TS).active is False


def test_missing_score_active_when_incomplete():
    ev = evaluate_missing_score({"risk_level": None, "risk_score": None}, TS)
    assert ev.active is True
    assert ev.insufficient_data is False


def test_missing_score_inactive_when_complete():
    ev = evaluate_missing_score({"risk_level": "baixo", "risk_score": 12}, TS)
    assert ev.active is False


def test_invalid_score_not_complete():
    ev = evaluate_risk_critical({"risk_level": "critico", "risk_score": float("nan")}, TS)
    assert ev.insufficient_data is True
    assert ev.active is False


def test_financial_delay_null_insufficient():
    ev = evaluate_financial_delay({"dias_atraso_boleto": None}, TS)
    assert ev.insufficient_data is True
    assert ev.active is False


def test_financial_delay_active_at_threshold():
    ev = evaluate_financial_delay({"dias_atraso_boleto": FINANCIAL_DELAY_DAYS_THRESHOLD}, TS)
    assert ev.active is True
    assert ev.insufficient_data is False


def test_financial_delay_below_threshold():
    ev = evaluate_financial_delay({"dias_atraso_boleto": FINANCIAL_DELAY_DAYS_THRESHOLD - 1}, TS)
    assert ev.active is False
    assert ev.insufficient_data is False


def test_financial_delay_invalid_type():
    ev = evaluate_financial_delay({"dias_atraso_boleto": True}, TS)
    assert ev.insufficient_data is True


def test_days_without_login_null():
    ev = evaluate_days_without_login({"dias_sem_login": None}, TS)
    assert ev.insufficient_data is True
    assert ev.active is False


def test_days_without_login_active():
    ev = evaluate_days_without_login({"dias_sem_login": DAYS_WITHOUT_LOGIN_THRESHOLD}, TS)
    assert ev.active is True


def test_risk_increase_needs_two_assessments():
    ev = evaluate_risk_increase([{"score": 40, "risk_level": "medio"}], TS)
    assert ev.insufficient_data is True
    assert ev.active is False


def test_risk_increase_model_change_not_increase():
    assessments = [
        {
            "score": 70,
            "risk_level": "critico",
            "model_version": "v2",
            "score_semantics_version": "risk-score-v1",
        },
        {
            "score": 40,
            "risk_level": "medio",
            "model_version": "v1",
            "score_semantics_version": "risk-score-v1",
        },
    ]
    ev = evaluate_risk_increase(assessments, TS)
    assert ev.active is False
    assert ev.insufficient_data is True
    assert ev.evidence["reason"] == "incomparable_model_or_semantics"


def test_risk_increase_score_delta():
    assessments = [
        {
            "score": 50 + RISK_INCREASE_SCORE_DELTA,
            "risk_level": "medio",
            "model_version": "v1",
            "score_semantics_version": "risk-score-v1",
        },
        {
            "score": 50,
            "risk_level": "medio",
            "model_version": "v1",
            "score_semantics_version": "risk-score-v1",
        },
    ]
    ev = evaluate_risk_increase(assessments, TS)
    assert ev.active is True
    assert ev.insufficient_data is False


def test_risk_increase_level_upgrade():
    assessments = [
        {
            "score": 52,
            "risk_level": "critico",
            "model_version": "v1",
            "score_semantics_version": "risk-score-v1",
        },
        {
            "score": 48,
            "risk_level": "medio",
            "model_version": "v1",
            "score_semantics_version": "risk-score-v1",
        },
    ]
    ev = evaluate_risk_increase(assessments, TS)
    assert ev.active is True


def test_student_can_have_multiple_active_signals():
    student = {
        "risk_level": "critico",
        "risk_score": 90,
        "dias_atraso_boleto": 30,
        "dias_sem_login": 40,
    }
    result = evaluate_student_signals(
        student_id="s1",
        tenant_id="t1",
        student=student,
        assessments=[],
    )
    active = set(result.active_ids())
    assert "risk_critical" in active
    assert "financial_delay" in active
    assert "days_without_login_elevated" in active
    assert "missing_score" not in active


def test_history_unavailable_flag():
    ev = evaluate_risk_increase([], TS, history_unavailable=True)
    assert ev.insufficient_data is True
    assert ev.evidence["reason"] == "history_schema_or_query_unavailable"
