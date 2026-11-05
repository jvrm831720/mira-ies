"""Small HTTP boundary for Composio APIs.

Keep the project API key server-side. Provider credentials stay in Composio.
"""
from __future__ import annotations

from typing import Any

import httpx


class ComposioNotConfigured(RuntimeError):
    """Composio is disabled or missing required project configuration."""


class ComposioAPIError(RuntimeError):
    """A sanitized error returned by the Composio API."""


class ComposioClient:
    def __init__(self, *, api_key: str, base_url: str = "https://backend.composio.dev", timeout: float = 20.0):
        if not api_key or not api_key.strip():
            raise ComposioNotConfigured("COMPOSIO_API_KEY não configurada.")
        self._api_key = api_key.strip()
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {"x-api-key": self._api_key, "accept": "application/json"}

    async def list_tools(self, *, toolkit_slug: str | None = None, search: str | None = None) -> dict[str, Any]:
        params: dict[str, str] = {}
        if toolkit_slug:
            params["toolkit_slug"] = toolkit_slug
        if search:
            params["search"] = search
        return await self._request("GET", "/api/v3.1/tools", params=params)

    async def create_auth_link(
        self, *, auth_config_id: str, user_id: str, alias: str,
    ) -> dict[str, Any]:
        payload = {"auth_config_id": auth_config_id, "user_id": user_id, "alias": alias}
        return await self._request("POST", "/api/v3/connected_accounts/link", json=payload)

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.request(
                    method, f"{self._base_url}{path}", headers=self._headers(), **kwargs
                )
                response.raise_for_status()
                data = response.json()
                if not isinstance(data, dict):
                    raise ComposioAPIError("Resposta inválida do Composio.")
                return data
        except httpx.HTTPStatusError as exc:
            # Do not propagate response bodies: providers can echo sensitive request data.
            raise ComposioAPIError(
                f"Composio respondeu com HTTP {exc.response.status_code}."
            ) from exc
        except httpx.TimeoutException as exc:
            raise ComposioAPIError("Tempo limite ao consultar Composio.") from exc
        except httpx.HTTPError as exc:
            raise ComposioAPIError("Falha de comunicação com Composio.") from exc
        except ValueError as exc:
            raise ComposioAPIError("Composio retornou JSON inválido.") from exc
