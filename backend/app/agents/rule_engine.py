"""Validação e avaliação pura da régua de retenção em JSON.

Este módulo não acessa banco nem envia mensagens. Ele transforma uma regra
versionada em uma decisão explicável; a persistência e a execução continuam
sob responsabilidade do orquestrador.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


RULE_SCHEMA_VERSION = 1

# Campos deliberadamente explícitos: regras não podem consultar atributos
# arbitrários do ORM nem dados de outro tenant.
FIELD_TYPES: dict[str, type | tuple[type, ...]] = {
    "risk_level": str,
    "risk_score": (int, float),
    "days_since_contact": int,
    "opt_out": bool,
    "has_phone": bool,
    "has_email": bool,
}
OPERATORS = {"eq", "neq", "gt", "gte", "lt", "lte", "in", "not_in"}


class RuleValidationError(ValueError):
    """A regra não obedece ao contrato suportado pelo motor."""


@dataclass(frozen=True)
class RuleDecision:
    matched: bool
    rule_id: str
    rule_version: int
    priority: int
    reason: str
    action: dict[str, Any] | None = None


def validate_rule(rule: Mapping[str, Any]) -> None:
    """Valida a estrutura e os tipos antes de salvar/ativar uma regra."""
    if not isinstance(rule, Mapping):
        raise RuleValidationError("A regra precisa ser um objeto JSON.")

    required = ("id", "name", "version", "conditions", "action")
    missing = [key for key in required if key not in rule]
    if missing:
        raise RuleValidationError(f"Campos obrigatórios ausentes: {', '.join(missing)}")

    if not isinstance(rule["id"], str) or not rule["id"].strip():
        raise RuleValidationError("'id' deve ser uma string não vazia.")
    if not isinstance(rule["name"], str) or not rule["name"].strip():
        raise RuleValidationError("'name' deve ser uma string não vazia.")
    if type(rule["version"]) is not int or rule["version"] < 1:
        raise RuleValidationError("'version' deve ser um inteiro >= 1.")
    priority = rule.get("priority", 100)
    if type(priority) is not int or priority < 0:
        raise RuleValidationError("'priority' deve ser um inteiro >= 0.")

    conditions = rule["conditions"]
    if not isinstance(conditions, Mapping) or set(conditions) - {"all", "any"}:
        raise RuleValidationError("'conditions' aceita apenas 'all' e/ou 'any'.")
    if not conditions or not any(conditions.values()):
        raise RuleValidationError("Informe ao menos uma condição em 'all' ou 'any'.")

    for group_name in ("all", "any"):
        group = conditions.get(group_name, [])
        if not isinstance(group, list):
            raise RuleValidationError(f"conditions.{group_name} deve ser uma lista.")
        for index, condition in enumerate(group):
            _validate_condition(condition, f"conditions.{group_name}[{index}]")

    action = rule["action"]
    if not isinstance(action, Mapping):
        raise RuleValidationError("'action' deve ser um objeto.")
    if action.get("channel") not in {"whatsapp", "email", "sms"}:
        raise RuleValidationError("action.channel deve ser whatsapp, email ou sms.")
    if not isinstance(action.get("template_id"), str) or not action["template_id"].strip():
        raise RuleValidationError("action.template_id deve ser uma string não vazia.")


def _validate_condition(condition: Any, path: str) -> None:
    if not isinstance(condition, Mapping):
        raise RuleValidationError(f"{path} deve ser um objeto.")
    if set(condition) != {"field", "op", "value"}:
        raise RuleValidationError(f"{path} deve conter somente field, op e value.")

    field = condition["field"]
    op = condition["op"]
    if field not in FIELD_TYPES:
        raise RuleValidationError(f"{path}: campo não permitido: {field!r}.")
    if op not in OPERATORS:
        raise RuleValidationError(f"{path}: operador não permitido: {op!r}.")

    value = condition["value"]
    if op in {"in", "not_in"}:
        if not isinstance(value, list) or not value:
            raise RuleValidationError(f"{path}: operador {op} exige lista não vazia.")
        expected = FIELD_TYPES[field]
        if not all(_value_has_type(item, expected) for item in value):
            raise RuleValidationError(f"{path}: tipo de valor incompatível com {field}.")
    elif not _value_has_type(value, FIELD_TYPES[field]):
        raise RuleValidationError(f"{path}: tipo de valor incompatível com {field}.")

    if op in {"gt", "gte", "lt", "lte"} and field not in {
        "risk_score", "days_since_contact"
    }:
        raise RuleValidationError(f"{path}: {op} só é válido para campos numéricos.")


def _value_has_type(value: Any, expected: type | tuple[type, ...]) -> bool:
    # bool é subclasse de int em Python; não deve passar como score/dias.
    if expected in {int, (int, float)} and isinstance(value, bool):
        return False
    return isinstance(value, expected)


def _condition_matches(condition: Mapping[str, Any], facts: Mapping[str, Any]) -> bool:
    field, op, expected = condition["field"], condition["op"], condition["value"]
    actual = facts.get(field)

    # Campo ausente não satisfaz nenhuma condição (inclusive neq), para não
    # transformar dados incompletos em elegibilidade acidental.
    if actual is None:
        return False
    if op == "eq":
        return actual == expected
    if op == "neq":
        return actual != expected
    if op == "gt":
        return actual > expected
    if op == "gte":
        return actual >= expected
    if op == "lt":
        return actual < expected
    if op == "lte":
        return actual <= expected
    if op == "in":
        return actual in expected
    if op == "not_in":
        return actual not in expected
    return False  # validação prévia torna este caminho inalcançável


def evaluate_rule(rule: Mapping[str, Any], facts: Mapping[str, Any]) -> RuleDecision:
    """Avalia uma regra e devolve um motivo legível para auditoria."""
    validate_rule(rule)
    conditions = rule["conditions"]
    all_conditions = conditions.get("all", [])
    any_conditions = conditions.get("any", [])

    all_ok = all(_condition_matches(c, facts) for c in all_conditions)
    any_ok = not any_conditions or any(_condition_matches(c, facts) for c in any_conditions)
    matched = all_ok and any_ok

    if matched:
        reason = f"Regra {rule['id']} v{rule['version']} correspondida."
    else:
        failed_all = [
            f"{c['field']} {c['op']} {c['value']!r}"
            for c in all_conditions if not _condition_matches(c, facts)
        ]
        any_descriptions = [
            f"{c['field']} {c['op']} {c['value']!r}" for c in any_conditions
        ]
        parts = []
        if failed_all:
            parts.append("condições obrigatórias não atendidas: " + ", ".join(failed_all))
        if any_conditions and not any(_condition_matches(c, facts) for c in any_conditions):
            parts.append("nenhuma condição alternativa atendida: " + ", ".join(any_descriptions))
        reason = f"Regra {rule['id']} v{rule['version']} não correspondida; " + "; ".join(parts) + "."

    return RuleDecision(
        matched=matched,
        rule_id=rule["id"],
        rule_version=rule["version"],
        priority=rule.get("priority", 100),
        reason=reason,
        action=dict(rule["action"]) if matched else None,
    )


def evaluate_rules(rules: list[Mapping[str, Any]], facts: Mapping[str, Any]) -> list[RuleDecision]:
    """Ordena por prioridade descendente e desempata de forma estável pelo ID."""
    seen_ids: set[str] = set()
    for rule in rules:
        validate_rule(rule)
        if rule["id"] in seen_ids:
            raise RuleValidationError(f"ID de regra duplicado no conjunto: {rule['id']}.")
        seen_ids.add(rule["id"])
    ordered = sorted(rules, key=lambda rule: (-rule.get("priority", 100), rule["id"]))
    return [evaluate_rule(rule, facts) for rule in ordered]
