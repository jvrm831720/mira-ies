"""Testes do contrato explícito de semântica financeira TOTVS RM."""

import pytest

from app.services.connectors.totvs_rm_finance import (
    RMFinancialStatus,
    TotvsRMFinancialStatusMap,
)


def test_unmapped_and_missing_financial_status_remain_unknown():
    mapping = TotvsRMFinancialStatusMap(
        status_field="STATUSLAN",
        codes={"1": RMFinancialStatus.PAID},
    )

    assert mapping.classify({"STATUSLAN": "1"}).status is RMFinancialStatus.PAID
    assert mapping.classify({"STATUSLAN": "2"}).status is RMFinancialStatus.UNKNOWN
    assert mapping.classify({}).status is RMFinancialStatus.UNKNOWN
    assert mapping.classify({"STATUSLAN": None}).status is RMFinancialStatus.UNKNOWN


def test_each_financial_state_requires_explicit_institution_mapping():
    mapping = TotvsRMFinancialStatusMap(
        status_field="SITUACAO_FINANCEIRA",
        codes={
            "A": RMFinancialStatus.OPEN,
            "P": RMFinancialStatus.PARTIALLY_PAID,
            "B": RMFinancialStatus.PAID,
            "C": RMFinancialStatus.CANCELLED,
            "R": RMFinancialStatus.RENEGOTIATED,
            "E": RMFinancialStatus.REVERSED,
        },
    )

    assert mapping.classify({"SITUACAO_FINANCEIRA": "P"}).status is RMFinancialStatus.PARTIALLY_PAID
    assert mapping.classify({"SITUACAO_FINANCEIRA": "C"}).status is RMFinancialStatus.CANCELLED
    assert mapping.classify({"SITUACAO_FINANCEIRA": "R"}).status is RMFinancialStatus.RENEGOTIATED
    assert mapping.classify({"SITUACAO_FINANCEIRA": "E"}).status is RMFinancialStatus.REVERSED


def test_mapping_rejects_unknown_as_an_explicit_source_code():
    with pytest.raises(ValueError, match="UNKNOWN"):
        TotvsRMFinancialStatusMap(
            status_field="STATUSLAN",
            codes={"?": RMFinancialStatus.UNKNOWN},
        )


@pytest.mark.parametrize("field", ["", "STATUS\nLAN"])
def test_mapping_rejects_invalid_source_field(field):
    with pytest.raises(ValueError):
        TotvsRMFinancialStatusMap(status_field=field, codes={})


def test_mapping_does_not_mutate_when_original_dict_changes():
    source = {"1": RMFinancialStatus.PAID}
    mapping = TotvsRMFinancialStatusMap(status_field="STATUSLAN", codes=source)
    source["2"] = RMFinancialStatus.OPEN

    assert mapping.classify({"STATUSLAN": "2"}).status is RMFinancialStatus.UNKNOWN
