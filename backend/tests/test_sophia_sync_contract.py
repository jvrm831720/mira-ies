"""Contract tests for SophiA sync normalization and queue safety."""
import pytest

from app.services.connectors.sophia_api import SophiaApiClient, SophiaApiConfig, SophiaContractError
from app.services.connectors.sophia_normalization import normalize_sophia_resource
from app.services.connectors.sophia_sync_worker import RESOURCES


def test_sync_resources_are_read_only_and_allowlisted():
    assert set(RESOURCES) == {"finance", "report_card", "recent_grades"}
    assert all(name.startswith("get_student_") for name in RESOURCES.values())


def test_finance_normalization_never_infers_balance_or_payment_state():
    normalized = normalize_sophia_resource("finance", [{
        "IdTitulo": 123, "ValorPrevisto": "100,00", "ValorPago": "40,00",
        "Pago": False, "DataVcto": "/Date(1735689600000)/",
    }])[0]
    assert normalized["raw"]["ValorPrevisto"] == "100,00"
    assert normalized["normalized"]["financial_state"] == "unknown"
    assert normalized["normalized"]["outstanding_balance"] is None


@pytest.mark.parametrize(("source", "expected"), [
    ("8,3", "8.3"), ("7.00", "7.00"), ("-1", None),
    ("-1,00", None), ("", None), (None, None), ("abc", None),
])
def test_grade_normalization_preserves_unknown_values(source, expected):
    row = normalize_sophia_resource("recent_grades", [{"Nota": source}])[0]
    assert row["normalized"]["grade_value"] == expected
    assert row["raw"]["Nota"] == source


def test_missing_grade_is_unknown_not_zero():
    row = normalize_sophia_resource("report_card", [{"Disciplina": "Matemática"}])[0]
    assert row["normalized"]["grade_value"] is None
    assert row["normalized"]["grade_value_known"] is False


@pytest.mark.parametrize("value", [None, {}, "not-a-list", [1, "x"]])
def test_invalid_collection_contract_fails_closed(value):
    with pytest.raises(SophiaContractError):
        SophiaApiClient._list_payload(value, "test")


def test_sophia_base_url_requires_https_and_versioned_path():
    config = SophiaApiConfig(
        base_url="https://sophia.example/serial/api/v1",
        username="integration", password="secret",
    )
    assert config.validated_base_url() == "https://sophia.example/serial/api/v1"
