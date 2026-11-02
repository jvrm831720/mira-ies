"""Read-only client for the official Sponte BI extraction API."""
from __future__ import annotations

from datetime import date
from typing import Any

import httpx

SPONTE_BASE_URL = "https://sponte-bi.sponteweb.com.br"
SPONTE_ENDPOINTS = (
    "alunos",
    "contratos",
    "contratosturmasestagios",
    "contasreceber",
    "notas",
    "fatofrequenciaalunosativos",
    "fatoalunosativos",
    "followups",
)


class SponteConnectionError(RuntimeError):
    pass


class SponteApiClient:
    def __init__(
        self,
        api_key: str,
        client_code: int,
        *,
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.api_key = api_key
        self.client_code = int(client_code)
        self._client = httpx.AsyncClient(
            base_url=SPONTE_BASE_URL,
            timeout=timeout,
            transport=transport,
            follow_redirects=False,
            headers={"x-api-key": api_key, "Accept": "application/json"},
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def fetch_page(
        self,
        endpoint: str,
        *,
        extraction_date: date,
        page_number: int = 1,
        page_size: int = 1000,
    ) -> dict[str, Any]:
        if endpoint not in SPONTE_ENDPOINTS:
            raise ValueError("Endpoint Sponte não permitido.")
        size = min(max(int(page_size), 1), 1000)
        try:
            response = await self._client.get(
                f"/api/v1/extracoes/{endpoint}",
                params={
                    "CodCliSponte": self.client_code,
                    "DataExtracao": extraction_date.isoformat(),
                    "PageNumber": max(1, int(page_number)),
                    "PageSize": size,
                },
            )
        except httpx.HTTPError as exc:
            raise SponteConnectionError(f"Falha de rede na API Sponte ({type(exc).__name__}).") from exc
        if response.status_code in {401, 403}:
            raise SponteConnectionError("API Key Sponte inválida ou sem acesso ao cliente informado.")
        if response.status_code == 429:
            raise SponteConnectionError("Limite de requisições da API Sponte atingido; tente novamente.")
        if response.status_code >= 500:
            raise SponteConnectionError(f"API Sponte indisponível (HTTP {response.status_code}).")
        if response.status_code >= 400:
            raise SponteConnectionError(f"API Sponte rejeitou a consulta (HTTP {response.status_code}).")
        try:
            payload = response.json()
        except ValueError as exc:
            raise SponteConnectionError("API Sponte retornou JSON inválido.") from exc
        if isinstance(payload, list):
            return {"items": payload, "hasNext": len(payload) == size}
        if not isinstance(payload, dict):
            raise SponteConnectionError("Formato de resposta Sponte não reconhecido.")
        items = payload.get("items")
        if not isinstance(items, list):
            raise SponteConnectionError(f"Resposta Sponte sem a lista 'items' no endpoint {endpoint}.")
        return payload

    async def fetch_all(
        self,
        endpoint: str,
        *,
        extraction_date: date,
        page_size: int = 1000,
        max_pages: int = 10000,
    ) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for page_number in range(1, max_pages + 1):
            payload = await self.fetch_page(
                endpoint, extraction_date=extraction_date,
                page_number=page_number, page_size=page_size,
            )
            items = [item for item in payload.get("items", []) if isinstance(item, dict)]
            records.extend(items)
            has_next = payload.get("hasNext")
            total_pages = payload.get("totalPages")
            if has_next is not None:
                if not bool(has_next):
                    return records
            elif total_pages is not None:
                if page_number >= int(total_pages):
                    return records
            elif not items or len(items) < min(page_size, 1000):
                return records
            if not items:
                return records
        raise SponteConnectionError(
            f"Limite de páginas atingido no endpoint {endpoint}; extração parcial não será confirmada."
        )

    async def test_connection(self) -> dict[str, Any]:
        payload = await self.fetch_page(
            "alunos", extraction_date=date.today(), page_number=1, page_size=1
        )
        return {
            "status": "connected",
            "endpoint": "alunos",
            "records_sampled": len(payload.get("items", [])),
            "client_code": self.client_code,
        }
