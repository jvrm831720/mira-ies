"""Read-only client for Isaac/Marlim bank reconciliation.

This is a payment-reconciliation source, not a WPensar academic ERP API.
Only the documented POST /v1/conciliation retrieval operation is exposed.
No seller creation, payment creation, refunds, or other write operations.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal
from urllib.parse import urlsplit

import httpx


ISAAC_MARLIM_BASE_URLS = {
    "sandbox": "https://sandbox.api.isaac.marlim.co",
    "production": "https://api.isaac.marlim.co",
}


class IsaacMarlimApiError(RuntimeError):
    """Base error for Isaac/Marlim API failures."""


class IsaacMarlimAuthenticationError(IsaacMarlimApiError):
    """API key rejected or missing permissions."""


class IsaacMarlimContractError(IsaacMarlimApiError):
    """Response does not match the documented API contract."""


@dataclass(frozen=True)
class IsaacMarlimConfig:
    api_key: str
    environment: Literal["sandbox", "production"]
    timeout_seconds: float = 30.0

    def base_url(self) -> str:
        if self.environment not in ISAAC_MARLIM_BASE_URLS:
            raise ValueError("Ambiente Isaac/Marlim inválido.")
        if not self.api_key or not self.api_key.strip():
            raise ValueError("API key Isaac/Marlim obrigatória.")
        if len(self.api_key) > 4096:
            raise ValueError("API key Isaac/Marlim excede o limite permitido.")
        if self.timeout_seconds <= 0:
            raise ValueError("Timeout deve ser positivo.")
        return ISAAC_MARLIM_BASE_URLS[self.environment]


@dataclass(frozen=True)
class IsaacMarlimTransaction:
    transaction_id: str
    item_id: str | None
    amount_cents: int
    date_created: str | None
    date_updated: str | None
    state: Literal["paid", "refunded"]


@dataclass(frozen=True)
class IsaacMarlimConciliation:
    reference_date: str | None
    paid_transactions_amount_cents: int
    refunded_transactions_amount_cents: int
    transfer_estimated_amount_cents: int
    transactions: tuple[IsaacMarlimTransaction, ...]
    page: int
    count: int


def _optional_string(value: Any, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise IsaacMarlimContractError(f"Campo inválido na resposta: {field}.")
    value = value.strip()
    return value or None


def _amount(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise IsaacMarlimContractError(f"Valor monetário inválido na resposta: {field}.")
    return value


def _parse_transactions(payload: dict[str, Any], key: str, state: Literal["paid", "refunded"]) -> list[IsaacMarlimTransaction]:
    rows = payload.get(key, [])
    if rows is None:
        return []
    if not isinstance(rows, list):
        raise IsaacMarlimContractError(f"Campo inválido na resposta: {key}.")
    result: list[IsaacMarlimTransaction] = []
    amount_key = "paid_amount" if state == "paid" else "refunded_amount"
    for row in rows:
        if not isinstance(row, dict):
            raise IsaacMarlimContractError(f"Registro inválido na resposta: {key}.")
        transaction_id = _optional_string(row.get("transaction_id"), "transaction_id")
        if not transaction_id:
            raise IsaacMarlimContractError("Transação sem transaction_id.")
        result.append(IsaacMarlimTransaction(
            transaction_id=transaction_id,
            item_id=_optional_string(row.get("item_id"), "item_id"),
            amount_cents=_amount(row.get(amount_key), amount_key),
            date_created=_optional_string(row.get("date_created"), "date_created"),
            date_updated=_optional_string(row.get("date_updated"), "date_updated"),
            state=state,
        ))
    return result


class IsaacMarlimApiClient:
    """Client restricted to the documented, read-only reconciliation endpoint."""

    def __init__(
        self,
        config: IsaacMarlimConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.config = config
        self._client = httpx.AsyncClient(
            base_url=config.base_url(),
            timeout=httpx.Timeout(config.timeout_seconds),
            follow_redirects=False,
            transport=transport,
            headers={
                "api_key": config.api_key,
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "IsaacMarlimApiClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def fetch_conciliation(
        self,
        *,
        date_created: datetime,
        with_transactions: bool = True,
        page: int = 1,
        count: int = 100,
    ) -> IsaacMarlimConciliation:
        if date_created.tzinfo is None or date_created.utcoffset() is None:
            raise ValueError("date_created deve conter timezone explícito.")
        if page < 1:
            raise ValueError("page deve ser maior ou igual a 1.")
        if not 1 <= count <= 100:
            raise ValueError("count deve estar entre 1 e 100.")

        request_body = {
            "date_created": date_created.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "with_transactions": bool(with_transactions),
            "page": page,
            "count": count,
        }
        try:
            response = await self._client.post("/v1/conciliation", json=request_body)
        except httpx.HTTPError as exc:
            raise IsaacMarlimApiError(
                f"Falha de transporte na API Isaac/Marlim ({type(exc).__name__})."
            ) from exc

        if response.status_code in {401, 403}:
            raise IsaacMarlimAuthenticationError(
                "API key Isaac/Marlim inválida ou sem permissão para conciliação."
            )
        if response.status_code >= 500:
            raise IsaacMarlimApiError(
                f"API Isaac/Marlim indisponível (HTTP {response.status_code})."
            )
        if response.status_code >= 400:
            raise IsaacMarlimApiError(
                f"API Isaac/Marlim rejeitou a consulta (HTTP {response.status_code})."
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise IsaacMarlimContractError("API Isaac/Marlim retornou JSON inválido.") from exc
        if not isinstance(payload, dict):
            raise IsaacMarlimContractError("Resposta de conciliação deve ser um objeto JSON.")

        reference_date = _optional_string(payload.get("transfer_reference_date"), "transfer_reference_date")
        transactions: list[IsaacMarlimTransaction] = []
        if with_transactions:
            transactions.extend(_parse_transactions(payload, "paid_transactions", "paid"))
            transactions.extend(_parse_transactions(payload, "refunded_transactions", "refunded"))

        return IsaacMarlimConciliation(
            reference_date=reference_date,
            paid_transactions_amount_cents=_amount(payload.get("paid_transactions_amount", 0), "paid_transactions_amount"),
            refunded_transactions_amount_cents=_amount(payload.get("refunded_transactions_amount", 0), "refunded_transactions_amount"),
            transfer_estimated_amount_cents=_amount(payload.get("transfer_estimated_amount", 0), "transfer_estimated_amount"),
            transactions=tuple(transactions),
            page=page,
            count=count,
        )
