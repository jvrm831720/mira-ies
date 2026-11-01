"""Testes puros do motor de grupos virtuais."""
from __future__ import annotations

from app.student_groups.catalog import GROUP_DEFINITIONS, OPERATIONAL_SIGNAL_IDS
from app.student_groups.evaluate import evaluate_student_groups

TS = "2026-11-01T12:00:00+00:00"


def _evaluate(student, assessments=None, history_unavailable=False):
    return evaluate_student_groups(
        student_id="s1",
        tenant_id="t1",
        student=student,
        assessments=assessments or [],
        history_unavailable=history_unavailable,
    )


def _by_id(result):
    return {group.group_id: group for group in result.groups}


def test_catalog_has_exactly_seven_groups():
    assert [item.id for item in GROUP_DEFINITIONS] == [
        "risk_critical",
        "risk_medium",
        "financial_delay",
        "days_without_login_elevated",
        "risk_increase",
        "multiple_active_signals",
        "missing_score",
    ]


def test_single_signal_groups_reuse_signal_semantics():
    groups = _by_id(
        _evaluate(
            {
                "risk_level": "critico",
                "risk_score": 90,
                "dias_atraso_boleto": 15,
                "dias_sem_login": 21,
            }
        )
    )
    assert groups["risk_critical"].state == "TRUE"
    assert groups["risk_medium"].state == "FALSE"
    assert groups["financial_delay"].state == "TRUE"
    assert groups["days_without_login_elevated"].state == "TRUE"
    assert groups["missing_score"].state == "FALSE"
    assert groups["risk_increase"].state == "INDETERMINATE"
    assert groups["multiple_active_signals"].state == "TRUE"


def test_missing_and_invalid_data_are_not_false():
    groups = _by_id(
        _evaluate(
            {
                "risk_level": None,
                "risk_score": None,
                "dias_atraso_boleto": None,
                "dias_sem_login": "invalid",
            }
        )
    )
    assert groups["missing_score"].state == "TRUE"
    assert groups["risk_critical"].state == "INDETERMINATE"
    assert groups["risk_medium"].state == "INDETERMINATE"
    assert groups["financial_delay"].state == "INDETERMINATE"
    assert groups["days_without_login_elevated"].state == "INDETERMINATE"
    assert groups["multiple_active_signals"].state == "INDETERMINATE"


def test_multiple_signals_excludes_missing_score():
    groups = _by_id(_evaluate({"risk_level": None, "risk_score": None}))
    assert groups["missing_score"].state == "TRUE"
    assert groups["multiple_active_signals"].state == "INDETERMINATE"
    assert groups["multiple_active_signals"].evidence["missing_score_excluded"] is True


def test_multiple_signals_false_when_fewer_than_two_can_become_active():
    groups = _by_id(
        _evaluate(
            {
                "risk_level": "baixo",
                "risk_score": 20,
                "dias_atraso_boleto": 0,
                "dias_sem_login": 0,
            },
            assessments=[
                {
                    "score": 20,
                    "risk_level": "baixo",
                    "model_version": "v1",
                    "score_semantics_version": "s1",
                },
                {
                    "score": 20,
                    "risk_level": "baixo",
                    "model_version": "v1",
                    "score_semantics_version": "s1",
                },
            ],
        )
    )
    assert groups["multiple_active_signals"].state == "FALSE"


def test_multiple_signals_indeterminate_when_unknown_can_reach_threshold():
    groups = _by_id(
        _evaluate(
            {
                "risk_level": "critico",
                "risk_score": 90,
                "dias_atraso_boleto": None,
                "dias_sem_login": 0,
            }
        )
    )
    assert groups["multiple_active_signals"].state == "INDETERMINATE"
    assert groups["multiple_active_signals"].evidence["active_count"] == 1
    assert groups["multiple_active_signals"].evidence["indeterminate_count"] == 2


def test_multiple_signals_true_with_two_definite_activations():
    groups = _by_id(
        _evaluate(
            {
                "risk_level": "medio",
                "risk_score": 60,
                "dias_atraso_boleto": 15,
                "dias_sem_login": 0,
            }
        )
    )
    assert groups["multiple_active_signals"].state == "TRUE"
    assert groups["multiple_active_signals"].evidence["active_count"] == 2


def test_risk_increase_requires_comparable_history():
    assessments = [
        {"score": 70, "risk_level": "critico", "model_version": "v1", "score_semantics_version": "s1"},
        {"score": 50, "risk_level": "medio", "model_version": "v1", "score_semantics_version": "s1"},
    ]
    groups = _by_id(_evaluate({"risk_level": "critico", "risk_score": 70}, assessments))
    assert groups["risk_increase"].state == "TRUE"
    assert groups["risk_increase"].evidence["signal_evidence"]["delta"] == 20.0


def test_history_failure_is_indeterminate_not_false():
    groups = _by_id(
        _evaluate(
            {"risk_level": "baixo", "risk_score": 10},
            history_unavailable=True,
        )
    )
    assert groups["risk_increase"].state == "INDETERMINATE"
    assert groups["risk_increase"].evidence["signal_evidence"]["reason"] == "history_schema_or_query_unavailable"


def test_operational_signal_set_is_explicit():
    assert set(OPERATIONAL_SIGNAL_IDS) == {
        "risk_critical",
        "risk_medium",
        "financial_delay",
        "days_without_login_elevated",
        "risk_increase",
    }
