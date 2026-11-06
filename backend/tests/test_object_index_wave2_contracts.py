"""Wave 2 contract tests for safe, global object-index filtering and sorting."""
from __future__ import annotations
import json
import pytest
from fastapi import HTTPException
from app.services.object_index_sorting import (
    parse_sort_terms, STUDENT_SORT_FIELDS, COLLECTION_SORT_FIELDS,
)
from app.services.collection_index_filters import compile_collection_filters


def test_multisort_order_and_limit_are_deterministic():
    assert parse_sort_terms("nome:asc,curso:desc,risk_score:asc", STUDENT_SORT_FIELDS) == [
        ("nome", "asc"), ("curso", "desc"), ("risk_score", "asc")
    ]
    assert parse_sort_terms(None, STUDENT_SORT_FIELDS) == []
    assert parse_sort_terms("balance:desc,status:asc", COLLECTION_SORT_FIELDS) == [
        ("balance", "desc"), ("status", "asc")
    ]


@pytest.mark.parametrize("raw", [
    "tenant_id:asc", "risk_score:ascending", "nome:asc,nome:desc",
    "nome:asc,curso:asc,matricula:asc,risk_score:desc",
    "nome:asc;DROP TABLE students", "nome", "nome:asc,,curso:desc",
])
def test_multisort_rejects_unapproved_operators_and_columns(raw):
    with pytest.raises(HTTPException) as exc:
        parse_sort_terms(raw, STUDENT_SORT_FIELDS)
    assert exc.value.status_code == 422


def test_no_financial_filter_can_change_tenant_scope_or_inject_sql():
    clauses, params, expanding = compile_collection_filters(json.dumps([
        {"key": "status", "op": "in", "value": ["open", "disputed"]},
        {"key": "balance", "op": "gt", "value": 10.5},
        {"key": "source", "op": "contains", "value": "%_\\acme"},
    ]))
    assert clauses[0] == "status IN :f0"
    assert clauses[1] == "balance > :f1"
    assert clauses[2].startswith("source ILIKE :f2")
    assert params["f0"] == ["open", "disputed"]
    assert str(params["f1"]) == "10.5"
    assert params["f2"].startswith("%")
    assert "\\%" in params["f2"] and "\\_" in params["f2"]
    assert expanding == ["f0"]
    assert all("tenant_id" not in clause for clause in clauses)


def test_financial_filters_keep_all_predicates_for_full_query():
    clauses, params, _ = compile_collection_filters(json.dumps([
        {"key": "updated_at", "op": "after", "value": "2026-11-01"},
        {"key": "status", "op": "eq", "value": "open"},
    ]))
    assert clauses == ["updated_at > :f0", "status = :f1"]
    assert params == {"f0": "2026-11-01", "f1": "open"}


@pytest.mark.parametrize("filter_spec", [
    [{"key": "tenant_id", "op": "eq", "value": "other-tenant"}],
    [{"key": "status", "op": "eq", "value": "nonexistent"}],
    [{"key": "balance", "op": "contains", "value": "0"}],
    [{"key": "balance", "op": "gt", "value": "0 OR 1=1"}],
    [{"key": "updated_at", "op": "before", "value": "not-a-date"}],
    [{"key": "source", "op": "in", "value": ["foo"]}],
    [{"key": "status", "op": "in", "value": ["open", "DROP TABLE"]}],
    [{"key": "status", "op": "empty", "value": "open"}],
])
def test_financial_filter_fail_closed(filter_spec):
    with pytest.raises(HTTPException) as exc:
        compile_collection_filters(json.dumps(filter_spec))
    assert exc.value.status_code == 422


def test_financial_filters_limit_count_and_input_size():
    excessive = [{"key": "status", "op": "eq", "value": "open"}] * 9
    with pytest.raises(HTTPException):
        compile_collection_filters(json.dumps(excessive))
    with pytest.raises(HTTPException):
        compile_collection_filters("a" * 2001)
