import pytest

from app.agents.rule_engine import (
    RuleValidationError,
    evaluate_rule,
    evaluate_rules,
    validate_rule,
)


def make_rule(**overrides):
    rule = {
        "id": "critical_48h",
        "name": "Críticos sem contato",
        "version": 1,
        "conditions": {
            "all": [
                {"field": "risk_level", "op": "eq", "value": "critico"},
                {"field": "days_since_contact", "op": "gte", "value": 7},
                {"field": "opt_out", "op": "eq", "value": False},
            ]
        },
        "action": {"channel": "whatsapp", "template_id": "critico_v1"},
    }
    rule.update(overrides)
    return rule


def test_rule_matches_and_returns_action():
    decision = evaluate_rule(
        make_rule(),
        {"risk_level": "critico", "days_since_contact": 8, "opt_out": False, "has_phone": True},
    )
    assert decision.matched is True
    assert decision.action == {"channel": "whatsapp", "template_id": "critico_v1"}
    assert "v1 correspondida" in decision.reason


def test_rule_does_not_match_and_explains_failed_condition():
    decision = evaluate_rule(
        make_rule(),
        {"risk_level": "medio", "days_since_contact": 8, "opt_out": False},
    )
    assert decision.matched is False
    assert decision.action is None
    assert "risk_level eq 'critico'" in decision.reason


def test_missing_fact_never_matches_neq():
    rule = make_rule(conditions={"all": [{"field": "opt_out", "op": "neq", "value": True}]})
    assert evaluate_rule(rule, {}).matched is False


@pytest.mark.parametrize("condition", [
    {"field": "tenant_id", "op": "eq", "value": "other-tenant"},
    {"field": "risk_level", "op": "execute", "value": "critico"},
    {"field": "days_since_contact", "op": "gte", "value": True},
    {"field": "opt_out", "op": "gte", "value": False},
])
def test_rejects_unknown_field_operator_or_type(condition):
    with pytest.raises(RuleValidationError):
        validate_rule(make_rule(conditions={"all": [condition]}))


def test_any_group_supports_alternatives():
    rule = make_rule(conditions={"all": [], "any": [
        {"field": "risk_level", "op": "eq", "value": "critico"},
        {"field": "risk_score", "op": "gte", "value": 90},
    ]})
    assert evaluate_rule(rule, {"risk_level": "medio", "risk_score": 94}).matched


def test_duplicate_rule_ids_rejected():
    rule = make_rule()
    with pytest.raises(RuleValidationError, match="duplicado"):
        evaluate_rules([rule, rule], {"risk_level": "critico", "days_since_contact": 8, "opt_out": False})


def test_invalid_channel_is_rejected():
    with pytest.raises(RuleValidationError, match="action.channel"):
        validate_rule(make_rule(action={"channel": "carrier_pigeon", "template_id": "x"}))
