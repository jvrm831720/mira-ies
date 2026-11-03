"""Transporte HTTP reutilizável e somente leitura para conectores ERP.

O módulo não conhece credenciais persistidas nem configurações de tenants.
O chamador deve fornecer credenciais e contexto já autorizados pela instituição.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx


class ConnectorConfigurationError(ValueError):
    """Configuração insegura ou inválida do conector."""


class ConnectorTransportError(RuntimeError):
    """Falha de transporte sem expor credenciais ou corpos da resposta."""


@dataclass(frozen=True, slots=True)
class ERPRequestContext:
    """Contexto multiempresa enviado em headers, quando exigido pelo ERP."""

    codcoligada: str | None = None
    codfilial: str | None = None
    codtipocurso: str | None = None
    codsistema: str | None = None

    def as_headers(self) -> dict[str, str]:
        values = {
            "CODCOLIGADA": self.codcoligada,
            "CODFILIAL": self.codfilial,
            "CODTIPOCURSO": self.codtipocurso,
            "CODSISTEMA": self.codsistema,
        }
        headers: dict[str, str] = {}
        for key, value in values.items():
            if value is None or not value.strip():
                continue
            clean = value.strip()
            if len(clean) > 128 or any(ord(char) < 32 or ord(char) == 127 for char in clean):
                raise ConnectorConfigurationError(f"Valor inválido para o contexto {key}.")
            headers[key] = clean
        return headers


class ReadOnlyRestClient:
    """Cliente REST que expõe exclusivamente GET e não segue redirects."""

    def __init__(
        self,
        *,
        base_url: str,
        username: str | None = None,
        password: str | None = None,
        context: ERPRequestContext | None = None,
        timeout_seconds: float = 20.0,
        allow_insecure_http: bool = False,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        parsed = urlsplit(base_url)
        if parsed.scheme not in {"https", "http"} or not parsed.netloc:
            raise ConnectorConfigurationError("URL base deve usar HTTP ou HTTPS.")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ConnectorConfigurationError("URL base não pode conter credenciais, query ou fragmento.")
        if parsed.scheme == "http" and not allow_insecure_http:
            raise ConnectorConfigurationError("HTTP sem TLS exige allow_insecure_http explícito.")
        if (username is None) != (password is None):
            raise ConnectorConfigurationError("Usuário e senha devem ser informados juntos.")
        if timeout_seconds <= 0:
            raise ConnectorConfigurationError("Timeout deve ser maior que zero.")

        headers = {
            "Accept": "application/json",
            "User-Agent": "MIRA-ERP-Connector/1.0",
        }
        if context is not None:
            headers.update(context.as_headers())

        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/") + "/",
            auth=httpx.BasicAuth(username, password) if username is not None else None,
            headers=headers,
            timeout=httpx.Timeout(timeout_seconds),
            follow_redirects=False,
            transport=transport,
        )

    @staticmethod
    def _validate_path(path: str) -> str:
        parsed = urlsplit(path)
        if (
            not path
            or parsed.scheme
            or parsed.netloc
            or parsed.query
            or parsed.fragment
            or "\\" in path
            or any(part == ".." for part in path.split("/"))
        ):
            raise ConnectorConfigurationError("Caminho deve ser relativo ao host e sem query.")
        return path.lstrip("/")

    async def get_json(
        self,
        path: str,
        *,
        params: Mapping[str, str | int | float] | None = None,
    ) -> Any:
        safe_path = self._validate_path(path)
        try:
            response = await self._client.get(safe_path, params=params)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ConnectorTransportError(
                f"ERP respondeu com HTTP {exc.response.status_code}."
            ) from None
        except httpx.RequestError:
            raise ConnectorTransportError("Falha de comunicação com o ERP.") from None

        try:
            return response.json()
        except ValueError:
            raise ConnectorTransportError("ERP retornou uma resposta que não é JSON válido.") from None

    async def iter_offset_pages(
        self,
        path: str,
        *,
        items_key: str,
        page_size: int = 100,
        start: int = 0,
        max_pages: int = 1000,
        query_params: Mapping[str, str | int | float] | None = None,
    ) -> AsyncIterator[list[Any]]:
        """Percorre páginas por offset sem descartar silenciosamente resultados."""
        if page_size < 1 or max_pages < 1 or start < 0:
            raise ConnectorConfigurationError("Parâmetros de paginação inválidos.")
        extra_params = dict(query_params or {})
        if any(key in {"start", "limit"} for key in extra_params):
            raise ConnectorConfigurationError("Parâmetros start e limit são reservados à paginação.")

        offset = start
        for _ in range(max_pages):
            payload = await self.get_json(
                path,
                params={"start": offset, "limit": page_size, **extra_params},
            )
            if isinstance(payload, list):
                items = payload
            elif isinstance(payload, dict) and isinstance(payload.get(items_key), list):
                items = payload[items_key]
            else:
                raise ConnectorTransportError(
                    f"Resposta paginada não contém uma lista em '{items_key}'."
                )

            if not items:
                return
            yield items
            if len(items) < page_size:
                return
            offset += len(items)

        raise ConnectorTransportError(
            "Limite de páginas atingido; sincronização interrompida para evitar truncamento."
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "ReadOnlyRestClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()
