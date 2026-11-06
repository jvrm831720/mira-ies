"""Safe SQL predicates for the read-only, tenant-scoped financial case index.

Only literal allowlisted column names/operators are interpolated. User input
is always typed, validated and bound to SQLAlchemy named parameters.
"""
from __future__ import annotations

import json
from datetime import date
from decimal import Decimal, InvalidOperation
from fastapi import HTTPException

FIELDS = {
    "external_ref": ("text", "external_ref"),
    "status": ("choice", "status"),
    "balance": ("number", "balance"),
    "source": ("text", "source"),
    "updated_at": ("date", "updated_at"),
}
OPS = {
    "text": {"eq", "neq", "contains", "not_contains", "starts_with", "empty"},
    "choice": {"eq", "neq", "in", "empty"},
    "number": {"eq", "gt", "lt", "between", "empty"},
    "date": {"before", "after", "between", "empty"},
}
STATUSES = {"open", "paid", "disputed", "agreement", "cancelled", "unknown"}


def fail() -> None:
    raise HTTPException(status_code=422, detail="Filtro financeiro inválido ou não permitido.")


def _typed(kind: str, value):
    if kind == "number":
        if isinstance(value, bool) or not isinstance(value, (float, int)):
            fail()
        try:
            result = Decimal(str(value))
        except InvalidOperation:
            fail()
        if not result.is_finite():
            fail()
        return result
    if not isinstance(value, str) or not value.strip() or len(value) > 150:
        fail()
    result = value.strip()
    if kind == "choice" and result not in STATUSES:
        fail()
    if kind == "date":
        if len(result) != 10:
            fail()
        try:
            date.fromisoformat(result)
        except ValueError:
            fail()
    return result


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def compile_collection_filters(raw: str | None) -> tuple[list[str], dict, list[str]]:
    if raw is None or raw == "":
        return [], {}, []
    if len(raw) > 2000:
        fail()
    try:
        items = json.loads(raw)
    except (ValueError, TypeError):
        fail()
    if not isinstance(items, list) or len(items) > 8:
        fail()

    sql: list[str] = []
    params: dict = {}
    expanding: list[str] = []
    for i, item in enumerate(items):
        if not isinstance(item, dict) or set(item) != {"key", "op", "value"}:
            fail()
        definition = FIELDS.get(item["key"]) if isinstance(item["key"], str) else None
        if not definition:
            fail()
        kind, column = definition
        op = item["op"]
        if not isinstance(op, str) or op not in OPS[kind]:
            fail()
        raw_value = item["value"]
        key = f"f{i}"
        if op == "empty":
            if raw_value is not None:
                fail()
            sql.append(f"{column} IS NULL")
            continue
        if op in {"between", "in"}:
            if not isinstance(raw_value, list) or not 1 <= len(raw_value) <= 12:
                fail()
            if op == "between" and len(raw_value) != 2:
                fail()
            values = [_typed(kind, value) for value in raw_value]
            if op == "in":
                sql.append(f"{column} IN :{key}")
                params[key] = values
                expanding.append(key)
            else:
                sql.append(f"{column} BETWEEN :{key}a AND :{key}b")
                params[key + "a"], params[key + "b"] = values
            continue
        value = _typed(kind, raw_value)
        params[key] = value
        if op == "contains":
            sql.append(f"{column} ILIKE :{key} ESCAPE '\\'")
            params[key] = "%" + _escape(value) + "%"
        elif op == "not_contains":
            sql.append(f"({column} IS NULL OR {column} NOT ILIKE :{key} ESCAPE '\\')")
            params[key] = "%" + _escape(value) + "%"
        elif op == "starts_with":
            sql.append(f"{column} ILIKE :{key} ESCAPE '\\'")
            params[key] = _escape(value) + "%"
        else:
            symbol = {
                "eq": "=", "neq": "!=", "gt": ">", "lt": "<",
                "before": "<", "after": ">",
            }.get(op)
            if not symbol:
                fail()
            sql.append(f"{column} {symbol} :{key}")
    return sql, params, expanding
