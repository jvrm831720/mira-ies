"""Semântica financeira configurável do TOTVS RM.

O RM permite parametrizações e códigos que variam por instalação. Este módulo
não presume que um status diferente de baixado seja "em aberto": só classifica
valores explicitamente mapeados pela instituição. Valores ausentes/desconhecidos
permanecem UNKNOWN. Não calcula saldo, atraso ou valor pago.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping


class RMFinancialStatus(StrEnum):
    UNKNOWN = "unknown"
    OPEN = "open"
    PARTIALLY_PAID = "partially_paid"
    PAID = "paid"
    CANCELLED = "cancelled"
    RENEGOTIATED = "renegotiated"
    REVERSED = "reversed"


@dataclass(frozen=True, slots=True)
class RMFinancialStatusResult:
    status: RMFinancialStatus
    source_field: str
    raw_value: str | None


@dataclass(frozen=True, slots=True)
class TotvsRMFinancialStatusMap:
    """Mapa de códigos homologados pela IES para um campo do payload RM."""

    status_field: str
    codes: Mapping[str, RMFinancialStatus]

    def __post_init__(self) -> None:
        field_name = self.status_field.strip()
        if not field_name or any(ord(char) < 32 for char in field_name):
            raise ValueError("Campo de status financeiro inválido.")

        normalized: dict[str, RMFinancialStatus] = {}
        for raw_code, status in self.codes.items():
            code = str(raw_code).strip()
            if not code or any(ord(char) < 32 for char in code):
                raise ValueError("Código de status financeiro inválido.")
            normalized_status = RMFinancialStatus(status)
            if normalized_status is RMFinancialStatus.UNKNOWN:
                raise ValueError("UNKNOWN é reservado para códigos sem mapeamento.")
            if code in normalized:
                raise ValueError("Código de status financeiro duplicado.")
            normalized[code] = normalized_status

        object.__setattr__(self, "status_field", field_name)
        object.__setattr__(self, "codes", MappingProxyType(normalized))

    def classify(self, record: Mapping[str, object]) -> RMFinancialStatusResult:
        value = record.get(self.status_field)
        if value is None:
            return RMFinancialStatusResult(
                status=RMFinancialStatus.UNKNOWN,
                source_field=self.status_field,
                raw_value=None,
            )

        raw_value = str(value).strip()
        status = self.codes.get(raw_value, RMFinancialStatus.UNKNOWN)
        return RMFinancialStatusResult(
            status=status,
            source_field=self.status_field,
            raw_value=raw_value,
        )
