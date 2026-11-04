"""Read-only client for SophiA Gestão Escolar Web API v1.

The documented API authenticates with a service account and returns an IP-bound
Token. Keep one client per configured institution/egress IP. Never log secrets
or token values.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import ipaddress
import os
from typing import Any
from urllib.parse import urlsplit

import httpx


class SophiaApiError(RuntimeError):
    """Base error for SophiA API failures."""


class SophiaAuthenticationError(SophiaApiError):
    """Credentials rejected or token could not be issued."""


class SophiaContractError(SophiaApiError):
    """Response does not match the documented API contract."""


READ_ENDPOINTS = {
    "units": "/Unidade/GetUnidades",
    "courses": "/Curso/GetCursos",
    "student_finance": "/FichaFinanceira/GetFichaFinanceira",
    "student_report_card": "/Boletim/GetTodasEtapasBoletim",
    "student_recent_grades": "/Nota/ListarNotasRecentes",
    "student_report_card_filter": "/Boletim/GetFiltroBoletim",
    "student_boleto": "/FichaFinanceira/GetBoleto",
}


@dataclass(frozen=True)
class SophiaApiConfig:
    # Full API root, including the installation serial and version path,
    # e.g. https://host.example/<serial>/api/v1.
    base_url: str
    username: str = field(repr=False)
    password: str = field(repr=False)
    user_agent: str = "MIRA-IES"
    timeout_seconds: float = 25.0

    def validated_base_url(self) -> str:
        parsed = urlsplit(self.base_url.strip())
        host = (parsed.hostname or "").lower()
        if (
            parsed.scheme != "https"
            or not host
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("SophiA API base URL must be an HTTPS URL without credentials, query or fragment.")
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            raise ValueError("SophiA API host must be a DNS hostname, not an IP literal.")
        if host in {"localhost", "metadata.google.internal"} or host.endswith((".localhost", ".local", ".internal")):
            raise ValueError("SophiA API host cannot target a local or metadata network.")
        if ".." in parsed.path or "%2e" in parsed.path.lower():
            raise ValueError("SophiA API base URL contains an unsafe path.")
        if not parsed.path.rstrip("/").lower().endswith("/v1"):
            raise ValueError("SophiA API base URL must include the installation API version path ending in /v1.")
        if not self.username.strip() or not self.password:
            raise ValueError("SophiA API integration username and password are required.")
        return self.base_url.rstrip("/")

    def validate_runtime_host(self) -> None:
        host = (urlsplit(self.base_url).hostname or "").lower()
        allowed = {
            item.strip().lower()
            for item in os.getenv("SOPHIA_ALLOWED_HOSTS", "").split(",")
            if item.strip()
        }
        if not allowed or host not in allowed:
            raise ValueError("SophiA host is not present in the explicit SOPHIA_ALLOWED_HOSTS allowlist.")


class SophiaApiClient:
    """Minimal read-only client for documented SophiA Gestão Escolar v1 routes."""

    def __init__(
        self,
        config: SophiaApiConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.config = config
        self.base_url = config.validated_base_url()
        self._token: str | None = None
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(config.timeout_seconds),
            follow_redirects=False,
            transport=transport,
            headers={
                "User-Agent": config.user_agent,
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "SophiaApiClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    @staticmethod
    def _json(response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError as exc:
            raise SophiaContractError("SophiA API returned a non-JSON response; JSON is required by this client.") from exc

    async def authenticate(self, *, force: bool = False) -> str:
        if self._token and not force:
            return self._token
        try:
            response = await self._client.post(
                "/Autenticacao/PostAutenticacao",
                json={"Usuario": self.config.username, "Senha": self.config.password},
            )
        except httpx.HTTPError as exc:
            raise SophiaApiError(f"SophiA authentication transport failure ({type(exc).__name__}).") from exc
        if response.status_code == 401:
            raise SophiaAuthenticationError("SophiA rejected the integration credentials.")
        if response.is_error:
            raise SophiaApiError(f"SophiA authentication failed with HTTP {response.status_code}.")
        payload = self._json(response)
        token = payload if isinstance(payload, str) else (
            payload.get("Token") or payload.get("token") if isinstance(payload, dict) else None
        )
        if not isinstance(token, str) or not token.strip():
            raise SophiaContractError("SophiA authentication response did not contain a token string.")
        self._token = token.strip()
        return self._token

    async def _get(self, route: str, *, params: dict[str, Any] | None = None) -> Any:
        if route not in READ_ENDPOINTS.values():
            raise ValueError("SophiA route is not in the read-only allowlist.")
        for attempt in range(2):
            token = await self.authenticate(force=attempt == 1)
            try:
                response = await self._client.get(route, params=params, headers={"Token": token})
            except httpx.HTTPError as exc:
                raise SophiaApiError(f"SophiA request transport failure ({type(exc).__name__}).") from exc
            if response.status_code == 401 and attempt == 0:
                self._token = None
                continue
            if response.status_code == 401:
                raise SophiaAuthenticationError("SophiA rejected the integration token after re-authentication.")
            if response.is_error:
                raise SophiaApiError(f"SophiA read request failed with HTTP {response.status_code}.")
            return self._json(response)
        raise SophiaAuthenticationError("SophiA authentication could not be renewed.")

    @staticmethod
    def _student_code(value: int | str) -> int:
        try:
            code = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("SophiA CodigoInterno must be a positive integer.") from exc
        if code <= 0:
            raise ValueError("SophiA CodigoInterno must be a positive integer.")
        return code

    async def get_units(self) -> list[dict[str, Any]]:
        payload = await self._get(READ_ENDPOINTS["units"])
        return self._list_payload(payload, "units")

    async def get_courses(self) -> list[dict[str, Any]]:
        payload = await self._get(READ_ENDPOINTS["courses"])
        return self._list_payload(payload, "courses")

    async def get_student_finance(self, codigo_interno: int | str) -> list[dict[str, Any]]:
        payload = await self._get(
            READ_ENDPOINTS["student_finance"],
            params={"codigo": self._student_code(codigo_interno)},
        )
        return self._list_payload(payload, "student finance")

    async def get_student_report_card(self, codigo_interno: int | str) -> list[dict[str, Any]]:
        payload = await self._get(
            READ_ENDPOINTS["student_report_card"],
            params={"codigo": self._student_code(codigo_interno)},
        )
        return self._list_payload(payload, "student report card")

    async def get_student_recent_grades(self, codigo_interno: int | str) -> list[dict[str, Any]]:
        payload = await self._get(
            READ_ENDPOINTS["student_recent_grades"],
            params={"codigo": self._student_code(codigo_interno)},
        )
        return self._list_payload(payload, "student recent grades")

    async def get_student_report_card_filter(self, codigo_interno: int | str) -> list[dict[str, Any]]:
        payload = await self._get(
            READ_ENDPOINTS["student_report_card_filter"],
            params={"codigo": self._student_code(codigo_interno)},
        )
        return self._list_payload(payload, "student report card filter")

    async def get_student_boleto(self, id_titulo: int | str) -> dict[str, Any]:
        try:
            title_id = int(id_titulo)
        except (TypeError, ValueError) as exc:
            raise ValueError("SophiA idTitulo must be a positive integer.") from exc
        if title_id <= 0:
            raise ValueError("SophiA idTitulo must be a positive integer.")
        payload = await self._get(READ_ENDPOINTS["student_boleto"], params={"idTitulo": title_id})
        if not isinstance(payload, dict):
            raise SophiaContractError("SophiA boleto response must be a JSON object.")
        return payload
    @staticmethod
    def _list_payload(payload: Any, resource: str) -> list[dict[str, Any]]:
        if not isinstance(payload, list):
            raise SophiaContractError(f"SophiA {resource} response must be a JSON array.")
        if any(not isinstance(item, dict) for item in payload):
            raise SophiaContractError(f"SophiA {resource} response contains a non-object item.")
        return payload
