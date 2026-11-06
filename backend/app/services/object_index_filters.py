"""Allowlisted declarative filters for Student Object Index.

No client-provided SQL columns, expressions, joins, or tenant scopes.
"""
from __future__ import annotations

import json
from datetime import date
from math import isfinite

from fastapi import HTTPException
from sqlalchemy import or_

from app.models.student import Student

FIELDS = {
    "nome": ("text", Student.nome),
    "matricula": ("text", Student.matricula),
    "curso": ("text", Student.curso),
    "risk_level": ("choice", Student.risk_level),
    "risk_score": ("number", Student.risk_score),
    "created_at": ("date", Student.created_at),
}
OPS = {
    "text": {"contains", "not_contains", "eq", "starts_with", "empty"},
    "choice": {"eq", "neq", "in", "empty"},
    "number": {"eq", "gt", "lt", "between", "empty"},
    "date": {"before", "after", "between", "empty"},
}
RISK_VALUES = {"baixo", "medio", "critico"}

def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

def _fail() -> None:
    raise HTTPException(status_code=422, detail="Filtro do índice inválido ou não autorizado.")

def _value(kind: str, value):
    if kind == "number":
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not isfinite(value):
            _fail()
        return float(value)
    if kind == "date":
        if not isinstance(value, str) or len(value) != 10:
            _fail()
        try:
            return date.fromisoformat(value)
        except ValueError:
            _fail()
    if not isinstance(value, str) or len(value) > 150 or not value.strip():
        _fail()
    return value.strip()

def compile_filters(raw: str | None) -> list:
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except (ValueError, TypeError):
        _fail()
    if not isinstance(payload, list) or len(payload) > 8:
        _fail()
    clauses = []
    for item in payload:
        if not isinstance(item, dict) or set(item) - {"key", "op", "value"}:
            _fail()
        definition = FIELDS.get(item.get("key"))
        if not definition:
            _fail()
        kind, column = definition
        op = item.get("op")
        if op not in OPS[kind]:
            _fail()
        raw_value = item.get("value")
        if op == "empty":
            if raw_value is not None:
                _fail()
            clauses.append(column.is_(None))
            continue
        if op in {"between", "in"}:
            if not isinstance(raw_value, list) or not 1 <= len(raw_value) <= 12:
                _fail()
            if op == "between" and len(raw_value) != 2:
                _fail()
            values = [_value(kind, v) for v in raw_value]
            if kind == "choice" and any(v not in RISK_VALUES for v in values):
                _fail()
            clauses.append(column.between(values[0], values[1]) if op == "between"
                           else column.in_(values))
            continue
        value = _value(kind, raw_value)
        if kind == "choice" and value not in RISK_VALUES:
            _fail()
        if op == "contains":
            clauses.append(column.ilike("%" + _escape(value) + "%", escape="\\"))
        elif op == "not_contains":
            clauses.append(or_(column.is_(None), ~column.ilike("%" + _escape(value) + "%", escape="\\")))
        elif op == "starts_with":
            clauses.append(column.ilike(_escape(value) + "%", escape="\\"))
        elif op == "eq":
            clauses.append(column == value)
        elif op == "neq":
            clauses.append(column != value)
        elif op == "gt":
            clauses.append(column > value)
        elif op == "lt":
            clauses.append(column < value)
        elif op == "before":
            clauses.append(column < value)
        elif op == "after":
            clauses.append(column > value)
    return clauses
