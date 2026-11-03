"""Contratos explícitos para Conta Corrente, acordos e vínculos de estorno RM.

Esta camada não presume DataServers, campos, códigos ou semântica universal.
Ela preserva movimentos e relações tipadas; não calcula saldo nem situação de
inadimplência. Todos os mapas de códigos devem ser homologados pela instituição.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping, Sequence

from app.services.connectors.totvs_rm_reconciliation import (
    RMFinancialReconciliation,
    RMSettlementEventKind,
)


class RMAgreementStatus(StrEnum):
    UNKNOWN = "unknown"
    PROPOSED = "proposed"
    ACTIVE = "active"
    SETTLED = "settled"
    CANCELLED = "cancelled"
    REPLACED = "replaced"


class RMObligationKind(StrEnum):
    UNKNOWN = "unknown"
    INSTALLMENT = "installment"
    LAUNCH = "launch"


class RMAgreementLinkRole(StrEnum):
    UNKNOWN = "unknown"
    ORIGINAL = "original"
    REPLACEMENT = "replacement"


class RMLedgerDirection(StrEnum):
    UNKNOWN = "unknown"
    DEBIT = "debit"
    CREDIT = "credit"


@dataclass(frozen=True, slots=True)
class RMCodeMap:
    """Mapa imutável e explícito para códigos de uma coluna da origem."""

    source_field: str
    codes: Mapping[str, StrEnum]
    unknown_value: StrEnum

    def __post_init__(self) -> None:
        field_name = self.source_field.strip()
        if not field_name or any(ord(char) < 32 for char in field_name):
            raise ValueError("Campo de mapeamento inválido.")
        normalized: dict[str, StrEnum] = {}
        for raw_code, raw_value in self.codes.items():
            code = str(raw_code).strip()
            if not code or any(ord(char) < 32 for char in code):
                raise ValueError("Código de origem inválido.")
            value = type(self.unknown_value)(raw_value)
            if value == self.unknown_value:
                raise ValueError("O valor UNKNOWN é reservado para códigos não mapeados.")
            if code in normalized:
                raise ValueError("Código de origem duplicado.")
            normalized[code] = value
        object.__setattr__(self, "source_field", field_name)
        object.__setattr__(self, "codes", MappingProxyType(normalized))

    def classify(self, record: Mapping[str, object]) -> StrEnum:
        raw_value = record.get(self.source_field)
        if raw_value is None:
            return self.unknown_value
        return self.codes.get(str(raw_value).strip(), self.unknown_value)


@dataclass(frozen=True, slots=True)
class RMAgreementFields:
    id_field: str
    student_ra_field: str
    contract_id_field: str
    status_map: RMCodeMap


@dataclass(frozen=True, slots=True)
class RMAgreementLinkFields:
    id_field: str
    agreement_ref_field: str
    obligation_ref_field: str
    obligation_kind_map: RMCodeMap
    role_map: RMCodeMap


@dataclass(frozen=True, slots=True)
class RMLedgerMovementFields:
    id_field: str
    student_ra_field: str
    contract_id_field: str
    amount_field: str
    direction_map: RMCodeMap
    source_ref_field: str | None = None


@dataclass(frozen=True, slots=True)
class RMReversalLinkFields:
    settlement_id_field: str
    original_settlement_ref_field: str


@dataclass(frozen=True, slots=True)
class RMAgreementNode:
    source_id: str
    student_ra: str
    contract_id: str
    status: RMAgreementStatus


@dataclass(frozen=True, slots=True)
class RMAgreementObligationLink:
    source_id: str
    agreement_ref: str
    obligation_ref: str
    obligation_kind: RMObligationKind
    role: RMAgreementLinkRole


@dataclass(frozen=True, slots=True)
class RMAgreementReconciliation:
    agreements: tuple[RMAgreementNode, ...]
    links: tuple[RMAgreementObligationLink, ...]
    links_without_agreement: tuple[str, ...]
    links_with_unknown_obligation: tuple[str, ...]
    links_with_unknown_role: tuple[str, ...]
    links_with_missing_obligation: tuple[str, ...]
    agreements_with_no_original: tuple[str, ...]
    agreements_with_no_replacement: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RMLedgerMovement:
    source_id: str
    student_ra: str
    contract_id: str
    amount: Decimal
    direction: RMLedgerDirection
    source_ref_raw: str | None


@dataclass(frozen=True, slots=True)
class RMLedgerAccountSummary:
    student_ra: str
    contract_id: str
    debit_total: Decimal
    credit_total: Decimal
    unknown_direction_total: Decimal
    movement_count: int


@dataclass(frozen=True, slots=True)
class RMLedgerReconciliation:
    movements: tuple[RMLedgerMovement, ...]
    account_summaries: tuple[RMLedgerAccountSummary, ...]


@dataclass(frozen=True, slots=True)
class RMReversalLink:
    reversal_item_id: str
    original_payment_item_id: str


@dataclass(frozen=True, slots=True)
class RMReversalReconciliation:
    links: tuple[RMReversalLink, ...]
    reversal_items_without_original: tuple[str, ...]
    invalid_reversal_targets: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RMWave23Result:
    agreements: RMAgreementReconciliation
    ledger: RMLedgerReconciliation
    reversals: RMReversalReconciliation


def _text(record: Mapping[str, object], field: str) -> str:
    value = record.get(field)
    if value is None:
        raise ValueError(f"Campo obrigatório ausente: {field}.")
    normalized = str(value).strip()
    if not normalized or any(ord(char) < 32 for char in normalized):
        raise ValueError(f"Campo obrigatório inválido: {field}.")
    return normalized


def _optional_text(record: Mapping[str, object], field: str | None) -> str | None:
    if field is None:
        return None
    value = record.get(field)
    if value is None or not str(value).strip():
        return None
    return str(value).strip()


def _money(record: Mapping[str, object], field: str) -> Decimal:
    raw = record.get(field)
    if raw is None or isinstance(raw, bool):
        raise ValueError(f"Valor monetário ausente ou inválido: {field}.")
    value = str(raw).strip()
    if not value or "," in value:
        raise ValueError(f"Valor monetário deve usar decimal canônico: {field}.")
    try:
        amount = Decimal(value)
    except (InvalidOperation, ValueError):
        raise ValueError(f"Valor monetário inválido: {field}.") from None
    if not amount.is_finite() or amount < 0:
        raise ValueError(f"Valor monetário deve ser finito e não negativo: {field}.")
    return amount


def _id(record: Mapping[str, object], field: str, seen: set[str], kind: str) -> str:
    value = _text(record, field)
    if value in seen:
        raise ValueError(f"ID duplicado em {kind}: {value}.")
    seen.add(value)
    return value


def reconcile_agreements(
    *,
    agreement_records: Sequence[Mapping[str, object]],
    link_records: Sequence[Mapping[str, object]],
    agreement_fields: RMAgreementFields,
    link_fields: RMAgreementLinkFields,
    financial: RMFinancialReconciliation,
) -> RMAgreementReconciliation:
    agreements: list[RMAgreementNode] = []
    agreement_ids: set[str] = set()
    for record in agreement_records:
        status = agreement_fields.status_map.classify(record)
        agreements.append(
            RMAgreementNode(
                source_id=_id(record, agreement_fields.id_field, agreement_ids, "acordo"),
                student_ra=_text(record, agreement_fields.student_ra_field),
                contract_id=_text(record, agreement_fields.contract_id_field),
                status=RMAgreementStatus(status),
            )
        )

    installments = {item.source_id: item for item in financial.installments}
    launches = {item.source_id: item for item in financial.launches}
    agreement_by_id = {item.source_id: item for item in agreements}
    links: list[RMAgreementObligationLink] = []
    link_ids: set[str] = set()
    without_agreement: list[str] = []
    unknown_obligation: list[str] = []
    unknown_role: list[str] = []
    missing_obligation: list[str] = []
    original_by_agreement: dict[str, set[str]] = {}
    replacement_by_agreement: dict[str, set[str]] = {}

    for record in link_records:
        link_id = _id(record, link_fields.id_field, link_ids, "vínculo de acordo")
        agreement_ref = _text(record, link_fields.agreement_ref_field)
        obligation_ref = _text(record, link_fields.obligation_ref_field)
        kind = RMObligationKind(link_fields.obligation_kind_map.classify(record))
        role = RMAgreementLinkRole(link_fields.role_map.classify(record))
        links.append(
            RMAgreementObligationLink(
                source_id=link_id,
                agreement_ref=agreement_ref,
                obligation_ref=obligation_ref,
                obligation_kind=kind,
                role=role,
            )
        )

        agreement = agreement_by_id.get(agreement_ref)
        if agreement is None:
            without_agreement.append(link_id)
            continue
        if kind is RMObligationKind.UNKNOWN:
            unknown_obligation.append(link_id)
            continue

        obligation = (
            installments.get(obligation_ref)
            if kind is RMObligationKind.INSTALLMENT
            else launches.get(obligation_ref)
        )
        if obligation is None:
            missing_obligation.append(link_id)
            continue
        if (
            obligation.student_ra != agreement.student_ra
            or obligation.contract_id != agreement.contract_id
        ):
            raise ValueError(
                f"Vínculo de acordo {link_id} conecta aluno/contrato diferentes."
            )
        if role is RMAgreementLinkRole.UNKNOWN:
            unknown_role.append(link_id)
        elif role is RMAgreementLinkRole.ORIGINAL:
            original_by_agreement.setdefault(agreement_ref, set()).add(
                f"{kind.value}:{obligation_ref}"
            )
        elif role is RMAgreementLinkRole.REPLACEMENT:
            replacement_by_agreement.setdefault(agreement_ref, set()).add(
                f"{kind.value}:{obligation_ref}"
            )

    return RMAgreementReconciliation(
        agreements=tuple(agreements),
        links=tuple(links),
        links_without_agreement=tuple(sorted(without_agreement)),
        links_with_unknown_obligation=tuple(sorted(unknown_obligation)),
        links_with_unknown_role=tuple(sorted(unknown_role)),
        links_with_missing_obligation=tuple(sorted(missing_obligation)),
        agreements_with_no_original=tuple(
            sorted(
                item.source_id
                for item in agreements
                if not original_by_agreement.get(item.source_id)
            )
        ),
        agreements_with_no_replacement=tuple(
            sorted(
                item.source_id
                for item in agreements
                if not replacement_by_agreement.get(item.source_id)
            )
        ),
    )


def reconcile_student_ledger(
    *,
    movement_records: Sequence[Mapping[str, object]],
    fields: RMLedgerMovementFields,
) -> RMLedgerReconciliation:
    movements: list[RMLedgerMovement] = []
    seen_ids: set[str] = set()
    totals: dict[tuple[str, str], dict[str, Decimal | int]] = {}

    for record in movement_records:
        source_id = _id(record, fields.id_field, seen_ids, "movimento de conta corrente")
        ra = _text(record, fields.student_ra_field)
        contract = _text(record, fields.contract_id_field)
        amount = _money(record, fields.amount_field)
        direction = RMLedgerDirection(fields.direction_map.classify(record))
        source_ref = _optional_text(record, fields.source_ref_field)
        movements.append(
            RMLedgerMovement(
                source_id=source_id,
                student_ra=ra,
                contract_id=contract,
                amount=amount,
                direction=direction,
                source_ref_raw=source_ref,
            )
        )

        key = (ra, contract)
        account = totals.setdefault(
            key,
            {
                "debit": Decimal("0"),
                "credit": Decimal("0"),
                "unknown": Decimal("0"),
                "count": 0,
            },
        )
        account["count"] = int(account["count"]) + 1
        if direction is RMLedgerDirection.DEBIT:
            account["debit"] = Decimal(account["debit"]) + amount
        elif direction is RMLedgerDirection.CREDIT:
            account["credit"] = Decimal(account["credit"]) + amount
        else:
            account["unknown"] = Decimal(account["unknown"]) + amount

    summaries = tuple(
        RMLedgerAccountSummary(
            student_ra=ra,
            contract_id=contract,
            debit_total=Decimal(values["debit"]),
            credit_total=Decimal(values["credit"]),
            unknown_direction_total=Decimal(values["unknown"]),
            movement_count=int(values["count"]),
        )
        for (ra, contract), values in sorted(totals.items())
    )
    return RMLedgerReconciliation(
        movements=tuple(movements),
        account_summaries=summaries,
    )


def reconcile_reversal_links(
    *,
    financial: RMFinancialReconciliation,
    fields: RMReversalLinkFields,
    settlement_source_records: Sequence[Mapping[str, object]],
) -> RMReversalReconciliation:
    """Vincula estorno a pagamento original sem calcular efeito líquido."""
    items = {item.source_id: item for item in financial.settlement_items}
    records_by_id: dict[str, Mapping[str, object]] = {}
    for record in settlement_source_records:
        source_id = _text(record, fields.settlement_id_field)
        if source_id in records_by_id:
            raise ValueError(f"ID duplicado em item de baixa para estorno: {source_id}.")
        records_by_id[source_id] = record

    links: list[RMReversalLink] = []
    without_original: list[str] = []
    invalid_targets: list[str] = []
    for item in financial.settlement_items:
        if item.event_kind is not RMSettlementEventKind.REVERSAL:
            continue
        record = records_by_id.get(item.source_id)
        original_ref = (
            _optional_text(record, fields.original_settlement_ref_field)
            if record is not None
            else None
        )
        if original_ref is None:
            without_original.append(item.source_id)
            continue
        original = items.get(original_ref)
        if (
            original is None
            or original.event_kind is not RMSettlementEventKind.PAYMENT
            or original.launch_ref != item.launch_ref
        ):
            invalid_targets.append(item.source_id)
            continue
        links.append(
            RMReversalLink(
                reversal_item_id=item.source_id,
                original_payment_item_id=original_ref,
            )
        )

    return RMReversalReconciliation(
        links=tuple(links),
        reversal_items_without_original=tuple(sorted(without_original)),
        invalid_reversal_targets=tuple(sorted(invalid_targets)),
    )


def reconcile_wave_23(
    *,
    financial: RMFinancialReconciliation,
    agreement_records: Sequence[Mapping[str, object]],
    agreement_link_records: Sequence[Mapping[str, object]],
    ledger_movement_records: Sequence[Mapping[str, object]],
    settlement_source_records: Sequence[Mapping[str, object]],
    agreement_fields: RMAgreementFields,
    agreement_link_fields: RMAgreementLinkFields,
    ledger_fields: RMLedgerMovementFields,
    reversal_fields: RMReversalLinkFields,
) -> RMWave23Result:
    """Executa reconciliações isoladas sem inferir saldo ou estado de acordo."""
    return RMWave23Result(
        agreements=reconcile_agreements(
            agreement_records=agreement_records,
            link_records=agreement_link_records,
            agreement_fields=agreement_fields,
            link_fields=agreement_link_fields,
            financial=financial,
        ),
        ledger=reconcile_student_ledger(
            movement_records=ledger_movement_records,
            fields=ledger_fields,
        ),
        reversals=reconcile_reversal_links(
            financial=financial,
            fields=reversal_fields,
            settlement_source_records=settlement_source_records,
        ),
    )
