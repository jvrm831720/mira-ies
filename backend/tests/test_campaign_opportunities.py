from app.services.campaign_opportunities import build_campaign_opportunities


def _group(group_id, name, matched=0, indeterminate=0, complete=True):
    return {
        "id": group_id,
        "name": name,
        "matched_count": matched,
        "indeterminate_count": indeterminate,
        "coverage": {"complete": complete},
    }


def test_recommendations_cover_all_seven_virtual_student_groups():
    groups = [
        _group("risk_critical", "Risco crítico", 10),
        _group("risk_medium", "Risco médio", 20),
        _group("financial_delay", "Atraso financeiro", 30),
        _group("days_without_login_elevated", "Dias sem login elevados", 40),
        _group("risk_increase", "Aumento relevante de risco", 50),
        _group("multiple_active_signals", "Múltiplos sinais ativos", 60),
        _group("missing_score", "Sem score", 70),
    ]

    opportunities = build_campaign_opportunities({"groups": groups})

    assert len(opportunities) == 7
    assert {item["group_id"] for item in opportunities} == {
        "risk_critical",
        "risk_medium",
        "financial_delay",
        "days_without_login_elevated",
        "risk_increase",
        "multiple_active_signals",
        "missing_score",
    }


def test_missing_score_is_data_quality_action_not_automated_outreach():
    opportunities = build_campaign_opportunities(
        {"groups": [_group("missing_score", "Sem score", matched=12)]}
    )

    assert len(opportunities) == 1
    item = opportunities[0]
    assert item["automatic_outreach_allowed"] is False
    assert item["recommended_channels"] == ["operacao_interna"]
    assert item["cadence_days"] == []
    assert "não gerar mensagem" in item["message_brief"].lower()


def test_reach_is_explicitly_an_unvalidated_upper_bound():
    opportunities = build_campaign_opportunities(
        {"groups": [_group("risk_critical", "Risco crítico", matched=15, indeterminate=4, complete=False)]}
    )

    reach = opportunities[0]["estimated_reach"]
    assert reach["upper_bound"] == 15
    assert reach["validated_contacts"] is False
    assert any("Cobertura incompleta" in item for item in opportunities[0]["safeguards"])


def test_groups_without_matches_or_indeterminate_cases_are_not_opportunities():
    opportunities = build_campaign_opportunities(
        {"groups": [_group("risk_medium", "Risco médio", matched=0, indeterminate=0)]}
    )

    assert opportunities == []
