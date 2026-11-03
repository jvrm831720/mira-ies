"""Testes sintéticos da reconciliação financeira RM sem códigos oficiais presumidos."""

from decimal import Decimal

import pytest

from app.services.connectors.totvs_rm_finance import (
    RMFinancialStatus,
    TotvsRMFinancialStatusMap,
)
from app.services.connectors.totvs_rm_reconciliation import (
    RMInstallmentFields,
    RMLaunchFields,
    RMSettlementEventKind,
    RMSettlementEventMap,
    RMSettlementFields,
    reconcile_financial_records,
)


@pytest.fixture
def field_maps():
    return {
        "installment": RMInstallmentFields(
            id_field="PARCELA_ID",
            student_ra_field="RA",
            contract_id_field="CONTRATO_ID",
            due_date_field="VENCIMENTO",
            nominal_amount_field="VALOR_NOMINAL",
        ),
        "launch": RMLaunchFields(
            id_field="LANCAMENTO_ID",
            installment_ref_field="PARCELA_REF",
            student_ra_field="RA",
            contract_id_field="CONTRATO_ID",
            original_amount_field="VALOR_ORIGINAL",
            due_date_field="VENCIMENTO",
            status_map=TotvsRMFinancialStatusMap(
                status_field="STATUSLAN",
                codes={
                    "OPEN_TEST": RMFinancialStatus.OPEN,
                    "PARTIAL_TEST": RMFinancialStatus.PARTIALLY_PAID,
                    "PAID_TEST": RMFinancialStatus.PAID,
                },
            ),
        ),
        "settlement": RMSettlementFields(
            id_field="ITEM_BAIXA_ID",
            launch_ref_field="LANCAMENTO_REF",
            amount_field="VALOR_BAIXA",
            event_date_field="DATA_BAIXA",
            event_map=RMSettlementEventMap(
                event_field="TIPO_EVENTO",
                codes={
                    "PAYMENT_TEST": RMSettlementEventKind.PAYMENT,
                    "REVERSAL_TEST": RMSettlementEventKind.REVERSAL,
                },
            ),
        ),
    }


def _installment(**overrides):
    row = {
        "PARCELA_ID": "PARC-1",
        "RA": "000045",
        "CONTRATO_ID": "CONT-7",
        "VENCIMENTO": "2026-10-10",
        "VALOR_NOMINAL": "1000.00",
    }
    return {**row, **overrides}


def _launch(**overrides):
    row = {
        "LANCAMENTO_ID": "LAN-1",
        "PARCELA_REF": "PARC-1",
        "RA": "000045",
        "CONTRATO_ID": "CONT-7",
        "VALOR_ORIGINAL": "1000.00",
        "VENCIMENTO": "2026-10-10",
        "STATUSLAN": "PARTIAL_TEST",
    }
    return {**row, **overrides}


def _settlement(**overrides):
    row = {
        "ITEM_BAIXA_ID": "BX-1",
        "LANCAMENTO_REF": "LAN-1",
        "VALOR_BAIXA": "300.00",
        "DATA_BAIXA": "2026-10-15T10:30:00",
        "TIPO_EVENTO": "PAYMENT_TEST",
    }
    return {**row, **overrides}


def _reconcile(field_maps, installments=None, launches=None, settlements=None):
    return reconcile_financial_records(
        installment_records=installments if installments is not None else [_installment()],
        launch_records=launches if launches is not None else [_launch()],
        settlement_records=settlements if settlements is not None else [_settlement()],
        installment_fields=field_maps["installment"],
        launch_fields=field_maps["launch"],
        settlement_fields=field_maps["settlement"],
    )


def test_reconciles_multiple_launches_and_partial_settlement_items(field_maps):
    result = _reconcile(
        field_maps,
        launches=[
            _launch(),
            _launch(
                LANCAMENTO_ID="LAN-2",
                VALOR_ORIGINAL="250.00",
                STATUSLAN="OPEN_TEST",
            ),
        ],
        settlements=[
            _settlement(VALOR_BAIXA="300.00"),
            _settlement(
                ITEM_BAIXA_ID="BX-2",
                VALOR_BAIXA="200.00",
                DATA_BAIXA="2026-10-20",
            ),
            _settlement(
                ITEM_BAIXA_ID="BX-3",
                VALOR_BAIXA="50.00",
                TIPO_EVENTO="REVERSAL_TEST",
            ),
            _settlement(
                ITEM_BAIXA_ID="BX-4",
                VALOR_BAIXA="10.00",
                TIPO_EVENTO="UNMAPPED_TEST",
            ),
        ],
    )

    assert len(result.installments) == 1
    assert len(result.launches) == 2
    assert result.launches[0].student_ra == "000045"
    assert result.launches[0].status is RMFinancialStatus.PARTIALLY_PAID
    first = next(item for item in result.launch_summaries if item.launch_id == "LAN-1")
    assert first.payment_items_total == Decimal("500.00")
    assert first.reversal_items_total == Decimal("50.00")
    assert first.unknown_items_total == Decimal("10.00")
    assert first.settlement_item_count == 4
    assert not hasattr(first, "balance")
    assert not hasattr(first, "net_paid")


def test_preserves_multiple_launches_linked_to_same_installment(field_maps):
    result = _reconcile(
        field_maps,
        launches=[
            _launch(LANCAMENTO_ID="LAN-1"),
            _launch(LANCAMENTO_ID="LAN-2", VALOR_ORIGINAL="200.00"),
        ],
        settlements=[],
    )

    assert [launch.source_id for launch in result.launches] == ["LAN-1", "LAN-2"]
    assert all(launch.installment_ref == "PARC-1" for launch in result.launches)


def test_orphan_relationships_are_reported_not_silently_dropped(field_maps):
    result = _reconcile(
        field_maps,
        launches=[_launch(PARCELA_REF="MISSING-PARC")],
        settlements=[_settlement(LANCAMENTO_REF="MISSING-LAN")],
    )

    assert result.launches_without_installment == ("LAN-1",)
    assert result.settlement_items_without_launch == ("BX-1",)


def test_rejects_launch_linked_to_different_student_or_contract(field_maps):
    with pytest.raises(ValueError, match="Vínculo inconsistente"):
        _reconcile(field_maps, launches=[_launch(RA="999999")])


@pytest.mark.parametrize(
    "field, value",
    [
        ("VALOR_ORIGINAL", "1.234,56"),
        ("VALOR_ORIGINAL", "-10.00"),
        ("VALOR_ORIGINAL", "NaN"),
        ("VALOR_ORIGINAL", "Infinity"),
        ("VALOR_ORIGINAL", True),
    ],
)
def test_rejects_ambiguous_or_invalid_money(field_maps, field, value):
    with pytest.raises(ValueError, match="Valor monetário"):
        _reconcile(field_maps, launches=[_launch(**{field: value})])


def test_rejects_duplicate_source_ids(field_maps):
    with pytest.raises(ValueError, match="ID duplicado"):
        _reconcile(
            field_maps,
            installments=[_installment(), _installment()],
        )


def test_missing_or_unknown_status_and_settlement_event_remain_unknown(field_maps):
    result = _reconcile(
        field_maps,
        launches=[_launch(STATUSLAN="NOT_HOMOLOGATED")],
        settlements=[_settlement(TIPO_EVENTO="NOT_HOMOLOGATED")],
    )

    assert result.launches[0].status is RMFinancialStatus.UNKNOWN
    assert result.settlement_items[0].event_kind is RMSettlementEventKind.UNKNOWN
    assert result.launch_summaries[0].unknown_items_total == Decimal("300.00")


def test_keeps_raw_dates_and_does_not_infer_timezone_or_date_format(field_maps):
    result = _reconcile(
        field_maps,
        installments=[_installment(VENCIMENTO="10/11/2026")],
        settlements=[_settlement(DATA_BAIXA="2026-11-10T23:00:00-03:00")],
    )

    assert result.installments[0].due_date_raw == "10/11/2026"
    assert result.settlement_items[0].event_date_raw == "2026-11-10T23:00:00-03:00"


def test_event_mapping_is_immutable_and_unknown_cannot_be_explicit(field_maps):
    source = {"P": RMSettlementEventKind.PAYMENT}
    event_map = RMSettlementEventMap(event_field="KIND", codes=source)
    source["R"] = RMSettlementEventKind.REVERSAL
    assert event_map.classify({"KIND": "R"}) is RMSettlementEventKind.UNKNOWN

    with pytest.raises(ValueError, match="UNKNOWN"):
        RMSettlementEventMap(
            event_field="KIND",
            codes={"?": RMSettlementEventKind.UNKNOWN},
        )
