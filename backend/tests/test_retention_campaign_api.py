"""Testes de contrato para o avaliador de campanhas.

A avaliação do JSON é coberta por test_retention_rule_engine.py; testes de integração
com Postgres/Redis devem ser executados no ambiente de CI da aplicação.
"""
from app.agents.rule_engine import RuleValidationError, evaluate_rules, validate_rule


def test_campaign_rule_set_can_contain_multiple_versioned_rules():
    rules = [
        {
            "id": "critical_48h", "name": "Críticos", "version": 1,
            "conditions": {"all": [
                {"field": "risk_level", "op": "eq", "value": "critico"},
                {"field": "opt_out", "op": "eq", "value": False},
            ]},
            "action": {"channel": "whatsapp", "template_id": "critico_v1"},
        },
        {
            "id": "risk_score_90", "name": "Score alto", "version": 1,
            "conditions": {"all": [
                {"field": "risk_score", "op": "gte", "value": 90},
                {"field": "opt_out", "op": "eq", "value": False},
            ]},
            "action": {"channel": "email", "template_id": "score_alto_v1"},
        },
    ]
    rules[0]["priority"] = 10
    rules[1]["priority"] = 80
    decisions = evaluate_rules(rules, {"risk_level": "critico", "risk_score": 94, "opt_out": False})
    assert [d.matched for d in decisions] == [True, True]
    assert [d.rule_id for d in decisions] == ["risk_score_90", "critical_48h"]
    assert [d.priority for d in decisions] == [80, 10]


def test_rule_rejects_unrecognized_fields_before_campaign_activation():
    rule = {
        "id": "unsafe", "name": "Unsafe", "version": 1,
        "conditions": {"all": [{"field": "tenant_id", "op": "eq", "value": "other"}]},
        "action": {"channel": "whatsapp", "template_id": "x"},
    }
    try:
        validate_rule(rule)
    except RuleValidationError:
        pass
    else:
        raise AssertionError("campo não permitido deveria invalidar a regra")
