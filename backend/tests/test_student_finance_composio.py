"""Wave 4 — finance-only Composio contracts. No live provider calls."""
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services import student_finance_composio as finance


def fields():
    return {
        "external_id": "id", "student_id": "student_id", "label": "title",
        "amount": "amount", "currency": "currency", "status": "status",
        "due_at": "due_at",
    }


def test_canonical_financial_rows_require_explicit_student_uuid_and_brl():
    student = str(uuid4())
    result = finance.normalize_financial({
        "items": [{
            "id": "B-42", "student_id": student, "title": "Mensalidade",
            "amount": "1450.25", "currency": "BRL", "status": "OPEN",
            "due_at": "2026-11-30T00:00:00-03:00", "secret": "discard-this",
        }],
    }, rows_path="items", fields=fields())
    assert result[0]["amount"] == Decimal("1450.25")
    assert result[0]["student_id"] == student
    assert result[0]["due_at"] == datetime(2026, 11, 30, 3, tzinfo=timezone.utc)
    assert "secret" not in str(result)


@pytest.mark.parametrize("invalid", [
    "-10", "1,234.00", "R$100", "1.999", "NaN", "Infinity", "1e7", True,
])
def test_amount_rejects_ambiguous_or_rounded_values(invalid):
    with pytest.raises(finance.FinancialReadDenied):
        finance.parse_amount(invalid)


def test_no_fuzzy_student_matching_and_no_payment_status_inference():
    row = {
        "id": "F-1", "student_id": "external-123", "title": "Fatura",
        "amount": "100.00", "currency": "BRL", "status": "unknown",
        "due_at": None,
    }
    with pytest.raises(finance.FinancialReadDenied, match="UUID"):
        finance.normalize_financial({"items": [row]}, rows_path="items", fields=fields())
    row["student_id"] = str(uuid4())
    row["currency"] = "USD"
    with pytest.raises(finance.FinancialReadDenied, match="BRL"):
        finance.normalize_financial({"items": [row]}, rows_path="items", fields=fields())


def test_unsafe_tool_slugs_denied_with_separate_finance_allowlist(monkeypatch):
    monkeypatch.setattr(finance, "get_settings", lambda: SimpleNamespace(
        student_finance_composio_read_tools="XERO_LIST_INVOICES,XERO_CREATE_PAYMENT",
    ))
    assert finance.allowed_tool("XERO_LIST_INVOICES")
    assert not finance.allowed_tool("XERO_CREATE_PAYMENT")
    assert not finance.allowed_tool("XERO_DELETE_INVOICE")
    assert not finance.allowed_tool("XERO_LIST_CONTACTS")


def test_finance_executor_is_off_by_default(monkeypatch):
    monkeypatch.setattr(finance, "get_settings", lambda: SimpleNamespace(
        student_finance_composio_enabled=False,
        native_academic_services_enabled=True,
        composio_enabled=True, composio_api_key="test", composio_identity_secret="test",
        student_finance_composio_read_tools="XERO_LIST_INVOICES",
    ))
    with pytest.raises(finance.FinancialReadDenied, match="desabilitada"):
        finance.enabled()


def test_due_date_requires_timezone():
    assert finance.parse_datetime(None) is None
    with pytest.raises(finance.FinancialReadDenied):
        finance.parse_datetime("2026-11-30T00:00:00")


@pytest.mark.parametrize("path", [
    "access_token", "credentials.password", "private_key",
    "financial.bank_account", "api_key",
])
def test_finance_mapping_rejects_sensitive_paths(path):
    with pytest.raises(finance.FinancialReadDenied):
        finance.safe_mapping_path(path)
