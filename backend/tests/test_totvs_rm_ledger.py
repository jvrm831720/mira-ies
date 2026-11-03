"""Testes sintéticos de Conta Corrente, acordos e vínculos de estorno RM."""

from decimal import Decimal

import pytest

from app.services.connectors.totvs_rm_finance import RMFinancialStatus
from app.services.connectors.totvs_rm_ledger import (
    RMAgreementFields,
    RMAgreementLinkFields,
    RMAgreementLinkRole,
    RMAgreementStatus,
    RMLedgerDirection,
    RMLedgerMovementFields,
    RMObligationKind,
    RMReversalLinkFields,
    RMCodeMap,
    reconcile_agreements,
    reconcile_reversal_links,
    reconcile_student_ledger,
)
from app.services.connectors.totvs_rm_reconciliation import (
    RMFinancialReconciliation,
    RMInstallmentNode,
    RMLaunchNode,
    RMLaunchSettlementSummary,
    RMSettlementEventKind,
    RMSettlementNode,
)


@pytest.fixture
def financial():
    return RMFinancialReconciliation(
        installments=(
            RMInstallmentNode(
                source_id="PARC-ORIGINAL",
                student_ra="000045",
                contract_id="CONT-7",
                due_date_raw="2026-10-10",
                nominal_amount=Decimal("1000.00"),
            ),
            RMInstallmentNode(
                source_id="PARC-ACORDO",
                student_ra="000045",
                contract_id="CONT-7",
                due_date_raw="2026-11-10",
                nominal_amount=Decimal("800.00"),
            ),
        ),
        launches=(
            RMLaunchNode(
                source_id="LAN-1",
                installment_ref="PARC-ORIGINAL",
                student_ra="000045",
                contract_id="CONT-7",
                due_date_raw="2026-10-10",
                original_amount=Decimal("1000.00"),
                status=RMFinancialStatus.PARTIALLY_PAID,
            ),
            RMLaunchNode(
                source_id="LAN-2",
                installment_ref="PARC-ACORDO",
                student_ra="000045",
                contract_id="CONT-7",
                due_date_raw="2026-11-10",
                original_amount=Decimal("800.00"),
                status=RMFinancialStatus.UNKNOWN,
            ),
        ),
        settlement_items=(
            RMSettlementNode(
                source_id="BX-PAY",
                launch_ref="LAN-1",
                amount=Decimal("300.00"),
                event_date_raw="2026-10-15",
                event_kind=RMSettlementEventKind.PAYMENT,
            ),
            RMSettlementNode(
                source_id="BX-REV",
                launch_ref="LAN-1",
                amount=Decimal("100.00"),
                event_date_raw="2026-10-16",
                event_kind=RMSettlementEventKind.REVERSAL,
            ),
        ),
        launch_summaries=(
            RMLaunchSettlementSummary(
                launch_id="LAN-1",
                payment_items_total=Decimal("300.00"),
                reversal_items_total=Decimal("100.00"),
                unknown_items_total=Decimal("0"),
                settlement_item_count=2,
            ),
        ),
        launches_without_installment=(),
        settlement_items_without_launch=(),
    )


@pytest.fixture
def agreement_maps():
    return (
        RMAgreementFields(
            id_field="ACORDO_ID",
            student_ra_field="RA",
            contract_id_field="CONTRATO",
            status_map=RMCodeMap(
                source_field="STATUS",
                codes={
                    "ACTIVE_TEST": RMAgreementStatus.ACTIVE,
                    "CANCEL_TEST": RMAgreementStatus.CANCELLED,
                },
                unknown_value=RMAgreementStatus.UNKNOWN,
            ),
        ),
        RMAgreementLinkFields(
            id_field="VINCULO_ID",
            agreement_ref_field="ACORDO_REF",
            obligation_ref_field="OBRIGACAO_REF",
            obligation_kind_map=RMCodeMap(
                source_field="OBRIGACAO_TIPO",
                codes={
                    "INSTALLMENT_TEST": RMObligationKind.INSTALLMENT,
                    "LAUNCH_TEST": RMObligationKind.LAUNCH,
                },
                unknown_value=RMObligationKind.UNKNOWN,
            ),
            role_map=RMCodeMap(
                source_field="PAPEL",
                codes={
                    "ORIGINAL_TEST": RMAgreementLinkRole.ORIGINAL,
                    "REPLACEMENT_TEST": RMAgreementLinkRole.REPLACEMENT,
                },
                unknown_value=RMAgreementLinkRole.UNKNOWN,
            ),
        ),
    )


def test_agreement_links_original_and_replacement_obligations(financial, agreement_maps):
    agreement_fields, link_fields = agreement_maps
    result = reconcile_agreements(
        agreement_records=[
            {
                "ACORDO_ID": "AC-1",
                "RA": "000045",
                "CONTRATO": "CONT-7",
                "STATUS": "ACTIVE_TEST",
            }
        ],
        link_records=[
            {
                "VINCULO_ID": "V-1",
                "ACORDO_REF": "AC-1",
                "OBRIGACAO_REF": "PARC-ORIGINAL",
                "OBRIGACAO_TIPO": "INSTALLMENT_TEST",
                "PAPEL": "ORIGINAL_TEST",
            },
            {
                "VINCULO_ID": "V-2",
                "ACORDO_REF": "AC-1",
                "OBRIGACAO_REF": "PARC-ACORDO",
                "OBRIGACAO_TIPO": "INSTALLMENT_TEST",
                "PAPEL": "REPLACEMENT_TEST",
            },
        ],
        agreement_fields=agreement_fields,
        link_fields=link_fields,
        financial=financial,
    )

    assert result.agreements[0].status is RMAgreementStatus.ACTIVE
    assert len(result.links) == 2
    assert result.agreements_with_no_original == ()
    assert result.agreements_with_no_replacement == ()


def test_unknown_agreement_status_and_relationships_are_not_inferred(
    financial, agreement_maps
):
    agreement_fields, link_fields = agreement_maps
    result = reconcile_agreements(
        agreement_records=[
            {
                "ACORDO_ID": "AC-2",
                "RA": "000045",
                "CONTRATO": "CONT-7",
                "STATUS": "NEW_CODE",
            }
        ],
        link_records=[
            {
                "VINCULO_ID": "V-3",
                "ACORDO_REF": "AC-2",
                "OBRIGACAO_REF": "PARC-ORIGINAL",
                "OBRIGACAO_TIPO": "NEW_KIND",
                "PAPEL": "NEW_ROLE",
            }
        ],
        agreement_fields=agreement_fields,
        link_fields=link_fields,
        financial=financial,
    )

    assert result.agreements[0].status is RMAgreementStatus.UNKNOWN
    assert result.links_with_unknown_obligation == ("V-3",)
    assert result.agreements_with_no_original == ("AC-2",)
    assert result.agreements_with_no_replacement == ("AC-2",)


def test_reports_missing_agreement_and_obligation_references(financial, agreement_maps):
    agreement_fields, link_fields = agreement_maps
    result = reconcile_agreements(
        agreement_records=[],
        link_records=[
            {
                "VINCULO_ID": "V-4",
                "ACORDO_REF": "MISSING-AGREEMENT",
                "OBRIGACAO_REF": "PARC-ORIGINAL",
                "OBRIGACAO_TIPO": "INSTALLMENT_TEST",
                "PAPEL": "ORIGINAL_TEST",
            }
        ],
        agreement_fields=agreement_fields,
        link_fields=link_fields,
        financial=financial,
    )
    assert result.links_without_agreement == ("V-4",)

    result = reconcile_agreements(
        agreement_records=[
            {
                "ACORDO_ID": "AC-3",
                "RA": "000045",
                "CONTRATO": "CONT-7",
                "STATUS": "ACTIVE_TEST",
            }
        ],
        link_records=[
            {
                "VINCULO_ID": "V-5",
                "ACORDO_REF": "AC-3",
                "OBRIGACAO_REF": "NOT-FOUND",
                "OBRIGACAO_TIPO": "INSTALLMENT_TEST",
                "PAPEL": "ORIGINAL_TEST",
            }
        ],
        agreement_fields=agreement_fields,
        link_fields=link_fields,
        financial=financial,
    )
    assert result.links_with_missing_obligation == ("V-5",)


def test_rejects_agreement_link_crossing_student_or_contract(financial, agreement_maps):
    agreement_fields, link_fields = agreement_maps
    with pytest.raises(ValueError, match="aluno/contrato"):
        reconcile_agreements(
            agreement_records=[
                {
                    "ACORDO_ID": "AC-4",
                    "RA": "999999",
                    "CONTRATO": "CONT-7",
                    "STATUS": "ACTIVE_TEST",
                }
            ],
            link_records=[
                {
                    "VINCULO_ID": "V-6",
                    "ACORDO_REF": "AC-4",
                    "OBRIGACAO_REF": "PARC-ORIGINAL",
                    "OBRIGACAO_TIPO": "INSTALLMENT_TEST",
                    "PAPEL": "ORIGINAL_TEST",
                }
            ],
            agreement_fields=agreement_fields,
            link_fields=link_fields,
            financial=financial,
        )


def test_ledger_totals_debits_credits_and_unknown_separately():
    fields = RMLedgerMovementFields(
        id_field="MOV_ID",
        student_ra_field="RA",
        contract_id_field="CONTRATO",
        amount_field="VALOR",
        direction_map=RMCodeMap(
            source_field="DIRECAO",
            codes={
                "D_TEST": RMLedgerDirection.DEBIT,
                "C_TEST": RMLedgerDirection.CREDIT,
            },
            unknown_value=RMLedgerDirection.UNKNOWN,
        ),
        source_ref_field="ORIGEM_REF",
    )
    result = reconcile_student_ledger(
        movement_records=[
            {
                "MOV_ID": "M-1",
                "RA": "000045",
                "CONTRATO": "CONT-7",
                "VALOR": "100.00",
                "DIRECAO": "D_TEST",
                "ORIGEM_REF": "LAN-1",
            },
            {
                "MOV_ID": "M-2",
                "RA": "000045",
                "CONTRATO": "CONT-7",
                "VALOR": "30.00",
                "DIRECAO": "C_TEST",
                "ORIGEM_REF": "BX-PAY",
            },
            {
                "MOV_ID": "M-3",
                "RA": "000045",
                "CONTRATO": "CONT-7",
                "VALOR": "5.00",
                "DIRECAO": "UNMAPPED",
            },
        ],
        fields=fields,
    )

    summary = result.account_summaries[0]
    assert summary.debit_total == Decimal("100.00")
    assert summary.credit_total == Decimal("30.00")
    assert summary.unknown_direction_total == Decimal("5.00")
    assert summary.movement_count == 3
    assert not hasattr(summary, "balance")
    assert not hasattr(summary, "net_balance")


def test_ledger_rejects_invalid_amount_and_duplicate_movement_id():
    fields = RMLedgerMovementFields(
        id_field="ID",
        student_ra_field="RA",
        contract_id_field="CONTRATO",
        amount_field="VALOR",
        direction_map=RMCodeMap(
            source_field="TIPO",
            codes={"D": RMLedgerDirection.DEBIT},
            unknown_value=RMLedgerDirection.UNKNOWN,
        ),
    )
    base = {"ID": "1", "RA": "000045", "CONTRATO": "C-1", "VALOR": "12.50", "TIPO": "D"}
    with pytest.raises(ValueError, match="Valor monetário"):
        reconcile_student_ledger(movement_records=[{**base, "VALOR": "-1"}], fields=fields)
    with pytest.raises(ValueError, match="ID duplicado"):
        reconcile_student_ledger(movement_records=[base, base], fields=fields)


def test_links_reversal_to_original_payment_and_flags_invalid_targets(financial):
    result = reconcile_reversal_links(
        financial=financial,
        fields=RMReversalLinkFields(
            settlement_id_field="ITEM_ID",
            original_settlement_ref_field="ESTORNO_DE",
        ),
        settlement_source_records=[
            {"ITEM_ID": "BX-PAY"},
            {"ITEM_ID": "BX-REV", "ESTORNO_DE": "BX-PAY"},
        ],
    )
    assert result.links[0].reversal_item_id == "BX-REV"
    assert result.links[0].original_payment_item_id == "BX-PAY"
    assert result.reversal_items_without_original == ()

    result = reconcile_reversal_links(
        financial=financial,
        fields=RMReversalLinkFields(
            settlement_id_field="ITEM_ID",
            original_settlement_ref_field="ESTORNO_DE",
        ),
        settlement_source_records=[
            {"ITEM_ID": "BX-PAY"},
            {"ITEM_ID": "BX-REV", "ESTORNO_DE": "BX-REV"},
        ],
    )
    assert result.invalid_reversal_targets == ("BX-REV",)


def test_reversal_without_reference_is_reported(financial):
    result = reconcile_reversal_links(
        financial=financial,
        fields=RMReversalLinkFields(
            settlement_id_field="ITEM_ID",
            original_settlement_ref_field="ESTORNO_DE",
        ),
        settlement_source_records=[{"ITEM_ID": "BX-PAY"}, {"ITEM_ID": "BX-REV"}],
    )
    assert result.reversal_items_without_original == ("BX-REV",)


def test_code_map_is_immutable_and_unknown_is_reserved():
    source = {"D": RMLedgerDirection.DEBIT}
    mapping = RMCodeMap(
        source_field="TIPO",
        codes=source,
        unknown_value=RMLedgerDirection.UNKNOWN,
    )
    source["C"] = RMLedgerDirection.CREDIT
    assert mapping.classify({"TIPO": "C"}) is RMLedgerDirection.UNKNOWN

    with pytest.raises(ValueError, match="UNKNOWN"):
        RMCodeMap(
            source_field="TIPO",
            codes={"?": RMLedgerDirection.UNKNOWN},
            unknown_value=RMLedgerDirection.UNKNOWN,
        )
