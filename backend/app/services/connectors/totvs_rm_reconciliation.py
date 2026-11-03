"""Reconciliação explícita de parcelas, lançamentos e itens de baixa do TOTVS RM.

Os nomes de campos são configuráveis pela IES. Este módulo não presume
semântica universal de DataServers, não calcula saldo devedor e não persiste
payloads brutos. Eventos de baixa e estorno são agregados separadamente.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping, Sequence

from app.services.connectors.totvs_rm_finance import (
    RMFinancialStatus,
    TotvsRMFinancialStatusMap,
)


class RMSettlementEventKind(StrEnum):
    UNKNOWN = "unknown"
    PAYMENT = "payment"
    REVERSAL = "reversal"


@dataclass(frozen=True, slots=True)
class RMSettlementEventMap:
    """Mapeamento de códigos de evento homologados pela instituição."""

    event_field: str
    codes: Mapping[str, RMSettlementEventKind]

    def __post_init__(self) -> None:
        field_name = self.event_field.strip()
        if not field_name or any(ord(char) < 32 for char in field_name):
            raise ValueError("Campo de evento de baixa inválido.")

        normalized: dict[str, RMSettlementEventKind] = {}
        for raw_code, event_kind in self.codes.items():
            code = str(raw_code).strip()
            if not code or any(ord(char) < 32 for char in code):
                raise ValueError("Código de evento de baixa inválido.")
            kind = RMSettlementEventKind(event_kind)
            if kind is RMSettlementEventKind.UNKNOWN:
                raise ValueError("UNKNOWN é reservado para eventos sem mapeamento.")
            if code in normalized:
                raise ValueError("Código de evento de baixa duplicado.")
            normalized[code] = kind

        object.__setattr__(self, "event_field", field_name)
        object.__setattr__(self, "codes", MappingProxyType(normalized))

    def classify(self, record: Mapping[str, object]) -> RMSettlementEventKind:
        value = record.get(self.event_field)
        if value is None:
            return RMSettlementEventKind.UNKNOWN
        return self.codes.get(str(value).strip(), RMSettlementEventKind.UNKNOWN)


@dataclass(frozen=True, slots=True)
class RMInstallmentFields:
    id_field: str
    student_ra_field: str
    contract_id_field: str
    due_date_field: str
    nominal_amount_field: str


@dataclass(frozen=True, slots=True)
class RMLaunchFields:
    id_field: str
    installment_ref_field: str
    student_ra_field: str
    contract_id_field: str
    original_amount_field: str
    due_date_field: str
    status_map: TotvsRMFinancialStatusMap


@dataclass(frozen=True, slots=True)
class RMSettlementFields:
    id_field: str
    launch_ref_field: str
    amount_field: str
    event_date_field: str
    event_map: RMSettlementEventMap


@dataclass(frozen=True, slots=True)
class RMInstallmentNode:
    source_id: str
    student_ra: str
    contract_id: str
    due_date_raw: str | None
    nominal_amount: Decimal


@dataclass(frozen=True, slots=True)
class RMLaunchNode:
    source_id: str
    installment_ref: str
    student_ra: str
    contract_id: str
    due_date_raw: str | None
    original_amount: Decimal
    status: RMFinancialStatus


@dataclass(frozen=True, slots=True)
class RMSettlementNode:
    source_id: str
    launch_ref: str
    amount: Decimal
    event_date_raw: str | None
    event_kind: RMSettlementEventKind


@dataclass(frozen=True, slots=True)
class RMLaunchSettlementSummary:
    launch_id: str
    payment_items_total: Decimal
    reversal_items_total: Decimal
    unknown_items_total: Decimal
    settlement_item_count: int


@dataclass(frozen=True, slots=True)
class RMFinancialReconciliation:
    installments: tuple[RMInstallmentNode, ...]
    launches: tuple[RMLaunchNode, ...]
    settlement_items: tuple[RMSettlementNode, ...]
    launch_summaries: tuple[RMLaunchSettlementSummary, ...]
    launches_without_installment: tuple[str, ...]
    settlement_items_without_launch: tuple[str, ...]


def _required_text(record: Mapping[str, object], field_name: str) -> str:
    value = record.get(field_name)
    if value is None:
        raise ValueError(f"Campo obrigatório ausente: {field_name}.")
    normalized = str(value).strip()
    if not normalized or any(ord(char) < 32 for char in normalized):
        raise ValueError(f"Campo obrigatório inválido: {field_name}.")
    return normalized


def _optional_raw_text(record: Mapping[str, object], field_name: str) -> str | None:
    value = record.get(field_name)
    if value is None or not str(value).strip():
        return None
    return str(value).strip()


def _amount(record: Mapping[str, object], field_name: str) -> Decimal:
    raw_value = record.get(field_name)
    if raw_value is None or isinstance(raw_value, bool):
        raise ValueError(f"Valor monetário ausente ou inválido: {field_name}.")
    raw_text = str(raw_value).strip()
    if not raw_text or "," in raw_text:
        raise ValueError(
            f"Valor monetário deve usar formato decimal canônico: {field_name}."
        )
    try:
        amount = Decimal(raw_text)
    except (InvalidOperation, ValueError):
        raise ValueError(f"Valor monetário inválido: {field_name}.") from None
    if not amount.is_finite() or amount < 0:
        raise ValueError(f"Valor monetário deve ser finito e não negativo: {field_name}.")
    return amount


def _unique_id(
    record: Mapping[str, object],
    field_name: str,
    seen: set[str],
    record_kind: str,
) -> str:
    source_id = _required_text(record, field_name)
    if source_id in seen:
        raise ValueError(f"ID duplicado em {record_kind}: {source_id}.")
    seen.add(source_id)
    return source_id


def reconcile_financial_records(
    *,
    installment_records: Sequence[Mapping[str, object]],
    launch_records: Sequence[Mapping[str, object]],
    settlement_records: Sequence[Mapping[str, object]],
    installment_fields: RMInstallmentFields,
    launch_fields: RMLaunchFields,
    settlement_fields: RMSettlementFields,
) -> RMFinancialReconciliation:
    """Constrói grafo financeiro a partir de campos explicitamente homologados.

    Uma parcela pode possuir vários lançamentos. Itens de baixa são vinculados
    ao lançamento, nunca diretamente à parcela. Valores de pagamento e estorno
    ficam separados: não se calcula valor líquido, saldo, atraso ou inadimplência.
    """
    installments: list[RMInstallmentNode] = []
    installment_ids: set[str] = set()
    for record in installment_records:
        installments.append(
            RMInstallmentNode(
                source_id=_unique_id(
                    record, installment_fields.id_field, installment_ids, "parcela"
                ),
                student_ra=_required_text(record, installment_fields.student_ra_field),
                contract_id=_required_text(record, installment_fields.contract_id_field),
                due_date_raw=_optional_raw_text(record, installment_fields.due_date_field),
                nominal_amount=_amount(record, installment_fields.nominal_amount_field),
            )
        )

    launches: list[RMLaunchNode] = []
    launch_ids: set[str] = set()
    for record in launch_records:
        launches.append(
            RMLaunchNode(
                source_id=_unique_id(record, launch_fields.id_field, launch_ids, "lançamento"),
                installment_ref=_required_text(record, launch_fields.installment_ref_field),
                student_ra=_required_text(record, launch_fields.student_ra_field),
                contract_id=_required_text(record, launch_fields.contract_id_field),
                due_date_raw=_optional_raw_text(record, launch_fields.due_date_field),
                original_amount=_amount(record, launch_fields.original_amount_field),
                status=launch_fields.status_map.classify(record).status,
            )
        )

    settlement_items: list[RMSettlementNode] = []
    settlement_ids: set[str] = set()
    for record in settlement_records:
        settlement_items.append(
            RMSettlementNode(
                source_id=_unique_id(
                    record, settlement_fields.id_field, settlement_ids, "item de baixa"
                ),
                launch_ref=_required_text(record, settlement_fields.launch_ref_field),
                amount=_amount(record, settlement_fields.amount_field),
                event_date_raw=_optional_raw_text(
                    record, settlement_fields.event_date_field
                ),
                event_kind=settlement_fields.event_map.classify(record),
            )
        )

    installments_by_id = {item.source_id: item for item in installments}
    launches_by_id = {item.source_id: item for item in launches}
    launches_without_installment: list[str] = []

    for launch in launches:
        installment = installments_by_id.get(launch.installment_ref)
        if installment is None:
            launches_without_installment.append(launch.source_id)
            continue
        if (
            launch.student_ra != installment.student_ra
            or launch.contract_id != installment.contract_id
        ):
            raise ValueError(
                f"Vínculo inconsistente entre lançamento {launch.source_id} "
                f"e parcela {launch.installment_ref}."
            )

    settlement_items_without_launch: list[str] = []
    summary_values: dict[str, dict[str, Decimal | int]] = {
        launch.source_id: {
            "payment": Decimal("0"),
            "reversal": Decimal("0"),
            "unknown": Decimal("0"),
            "count": 0,
        }
        for launch in launches
    }

    for item in settlement_items:
        if item.launch_ref not in launches_by_id:
            settlement_items_without_launch.append(item.source_id)
            continue
        summary = summary_values[item.launch_ref]
        summary["count"] = int(summary["count"]) + 1
        if item.event_kind is RMSettlementEventKind.PAYMENT:
            summary["payment"] = Decimal(summary["payment"]) + item.amount
        elif item.event_kind is RMSettlementEventKind.REVERSAL:
            summary["reversal"] = Decimal(summary["reversal"]) + item.amount
        else:
            summary["unknown"] = Decimal(summary["unknown"]) + item.amount

    summaries = tuple(
        RMLaunchSettlementSummary(
            launch_id=launch_id,
            payment_items_total=Decimal(values["payment"]),
            reversal_items_total=Decimal(values["reversal"]),
            unknown_items_total=Decimal(values["unknown"]),
            settlement_item_count=int(values["count"]),
        )
        for launch_id, values in sorted(summary_values.items())
    )

    return RMFinancialReconciliation(
        installments=tuple(installments),
        launches=tuple(launches),
        settlement_items=tuple(settlement_items),
        launch_summaries=summaries,
        launches_without_installment=tuple(sorted(launches_without_installment)),
        settlement_items_without_launch=tuple(sorted(settlement_items_without_launch)),
    )
