"""Read-only Omie API client with server-side access-token refresh."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx


OMIE_API_BASE = "https://app.omie.com.br"
OMIE_REFRESH_BASE = "https://app.omie.com.br/api/portal/apps"


class OmieApiError(RuntimeError):
    def __init__(self, message: str, *, code: str = "omie_api_error", retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


@dataclass(slots=True)
class OmieCredentials:
    app_hash: str
    access_token: str
    refresh_token: str
    expires_at: datetime


class OmieApiClient:
    """Allowlisted read-only client; no financial write operation is exposed."""

    def __init__(
        self,
        credentials: OmieCredentials,
        *,
        http_client: httpx.AsyncClient | None = None,
    ):
        self.credentials = credentials
        self._http = http_client or httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0))
        self._owns_http = http_client is None

    async def close(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    async def _refresh_if_needed(self) -> None:
        now = datetime.now(timezone.utc)
        expires_at = self.credentials.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at > now + timedelta(minutes=5):
            return

        url = f"{OMIE_REFRESH_BASE}/{self.credentials.app_hash}/refresh-token/"
        try:
            response = await self._http.post(
                url,
                json={
                    "token": self.credentials.access_token,
                    "refresh_token": self.credentials.refresh_token,
                },
                headers={"Content-Type": "application/json"},
            )
        except httpx.HTTPError as exc:
            raise OmieApiError("Não foi possível renovar a sessão Omie.", code="refresh_transport_error", retryable=True) from exc
        if response.status_code >= 400:
            raise OmieApiError("A renovação do token Omie foi recusada.", code=f"refresh_http_{response.status_code}")
        try:
            payload = response.json()
            access_token = payload["token"]
            refresh_token = payload["refresh_token"]
        except (ValueError, KeyError, TypeError) as exc:
            raise OmieApiError("Resposta de renovação Omie inválida.", code="invalid_refresh_response") from exc
        if not isinstance(access_token, str) or not access_token or not isinstance(refresh_token, str) or not refresh_token:
            raise OmieApiError("Resposta de renovação Omie inválida.", code="invalid_refresh_response")

        self.credentials.access_token = access_token
        self.credentials.refresh_token = refresh_token
        self.credentials.expires_at = now + timedelta(hours=24)

    async def _call(self, endpoint: str, operation: str, params: dict[str, Any]) -> dict[str, Any]:
        await self._refresh_if_needed()
        url = f"{OMIE_API_BASE}{endpoint}"
        try:
            response = await self._http.post(
                url,
                json={"call": operation, "param": [params]},
                headers={
                    "Authorization": f"Bearer {self.credentials.access_token}",
                    "Content-Type": "application/json",
                },
            )
        except httpx.HTTPError as exc:
            raise OmieApiError("Falha de comunicação com a API Omie.", code="transport_error", retryable=True) from exc

        if response.status_code in (425, 429, 503):
            raise OmieApiError("A API Omie está temporariamente indisponível ou limitou as chamadas.", code=f"http_{response.status_code}", retryable=True)
        if response.status_code >= 400:
            raise OmieApiError("A API Omie recusou a consulta.", code=f"http_{response.status_code}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise OmieApiError("A API Omie retornou uma resposta inválida.", code="invalid_json") from exc
        if not isinstance(payload, dict):
            raise OmieApiError("A API Omie retornou uma estrutura inesperada.", code="invalid_payload")
        if str(payload.get("faultcode") or payload.get("status") or "") not in ("", "0", "200", "OK"):
            raise OmieApiError("A API Omie retornou um erro de negócio.", code="omie_business_error")
        return payload

    async def list_accounts_receivable(self, *, page: int = 1, page_size: int = 50) -> dict[str, Any]:
        return await self._call(
            "/api/v1/financas/contareceber/",
            "ListarContasReceber",
            {"pagina": page, "registros_por_pagina": page_size},
        )

    async def list_accounts_payable(self, *, page: int = 1, page_size: int = 50) -> dict[str, Any]:
        return await self._call(
            "/api/v1/financas/contapagar/",
            "ListarContasPagar",
            {"pagina": page, "registros_por_pagina": page_size},
        )
