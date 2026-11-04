"""Cliente read-only para a WebAPI de views do GVcollege.

A documentação pública não define autenticação nem schemas universais.
Por isso, autenticação é injetada pelo provedor institucional de segredos e
cada view/coluna precisa de contrato explícito por tenant.
"""
from __future__ import annotations

import ipaddress
import json
import math
import re
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any
from urllib.parse import quote, urlsplit

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.connectors.tenant_destinations import (
    _destination_authorization_token,
    authorize_tenant_destination,
    require_destination_authorization,
)


_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_HEADER_NAME = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")
_ALLOWED_OPERATORS = {"eq", "ne", "gt", "ge", "lt", "le"}


class GvcollegeConfigurationError(ValueError):
    """Configuração institucional inválida ou incompleta."""


class GvcollegeAPIError(RuntimeError):
    """Resposta inválida ou erro HTTP da WebAPI GVcollege."""


@dataclass(frozen=True)
class GvcollegeViewContract:
    """Contrato institucional de uma view dbo.GVMVW_*.

    view_name usa o nome curto esperado pela API (ex.: 'Pessoa'), sem dbo.
    nem o prefixo GVMVW_. Os campos são declarados pela instituição.
    """

    view_name: str
    source_fields: tuple[str, ...]
    pagination_key: str
    field_mapping: Mapping[str, str] = field(default_factory=dict)
    default_order_by: str | None = None

    def __post_init__(self) -> None:
        if not _IDENTIFIER.fullmatch(self.view_name):
            raise GvcollegeConfigurationError("Nome de view inválido")
        if self.view_name.lower().startswith(("dbo_", "gvmvw_")):
            raise GvcollegeConfigurationError(
                "Use o nome curto da view, sem dbo/GVMVW_"
            )
        if not self.source_fields:
            raise GvcollegeConfigurationError("A view precisa declarar campos")
        if self.pagination_key not in self.source_fields:
            raise GvcollegeConfigurationError("pagination_key deve ser campo contratado")
        if any(not _IDENTIFIER.fullmatch(name) for name in self.source_fields):
            raise GvcollegeConfigurationError("Campo de origem inválido")
        if len(set(self.source_fields)) != len(self.source_fields):
            raise GvcollegeConfigurationError("Campos de origem duplicados")
        if self.default_order_by and self.default_order_by != self.pagination_key:
            raise GvcollegeConfigurationError("default_order_by deve ser a chave única de paginação")
        if any(
            target not in self.source_fields
            for target in self.field_mapping.values()
        ):
            raise GvcollegeConfigurationError(
                "Mapeamento aponta para campo não declarado"
            )


@dataclass(frozen=True)
class GvcollegeInstitutionConfig:
    tenant_id: str
    base_url: str
    allowed_hosts: frozenset[str]
    views: Mapping[str, GvcollegeViewContract]
    page_size: int = 500
    timeout_seconds: float = 20.0
    max_response_bytes: int = 5_000_000

    def __post_init__(self) -> None:
        if not self.tenant_id.strip():
            raise GvcollegeConfigurationError("tenant_id obrigatório")
        parsed = urlsplit(self.base_url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in ("", "/")
            or parsed.port not in (None, 443)
        ):
            raise GvcollegeConfigurationError(
                "base_url deve ser HTTPS, sem credenciais, query ou fragmento"
            )
        host = parsed.hostname.rstrip(".").lower()
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        if address and (
            address.is_private or address.is_loopback or address.is_link_local
            or address.is_reserved or address.is_unspecified
        ):
            raise GvcollegeConfigurationError("IP privado/reservado não permitido")
        normalized = frozenset(item.rstrip(".").lower() for item in self.allowed_hosts)
        if not normalized or host not in normalized:
            raise GvcollegeConfigurationError(
                "Hostname não consta na allowlist exata da instituição"
            )
        if not 1 <= self.page_size <= 1000:
            raise GvcollegeConfigurationError("page_size deve estar entre 1 e 1000")
        if (
            not math.isfinite(self.timeout_seconds)
            or self.timeout_seconds <= 0
            or not isinstance(self.max_response_bytes, int)
            or isinstance(self.max_response_bytes, bool)
            or self.max_response_bytes <= 0
        ):
            raise GvcollegeConfigurationError("Limites HTTP devem ser positivos e finitos")
        if not self.views:
            raise GvcollegeConfigurationError("Nenhuma view foi homologada")
        object.__setattr__(self, "allowed_hosts", normalized)
        object.__setattr__(self, "base_url", self.base_url.rstrip("/"))


@dataclass(frozen=True)
class ODataFilter:
    field: str
    operator: str
    value: str | int | float | bool

    def render(self, contract: GvcollegeViewContract) -> str:
        if self.field not in contract.source_fields:
            raise GvcollegeConfigurationError("Filtro usa campo fora do contrato")
        if self.operator not in _ALLOWED_OPERATORS:
            raise GvcollegeConfigurationError("Operador OData não permitido")
        if isinstance(self.value, bool):
            value = "true" if self.value else "false"
        elif isinstance(self.value, float):
            if not math.isfinite(self.value):
                raise GvcollegeConfigurationError("Filtro numérico deve ser finito")
            value = str(self.value)
        elif isinstance(self.value, int):
            value = str(self.value)
        elif isinstance(self.value, str):
            value = "'" + self.value.replace("'", "''") + "'"
        else:
            raise GvcollegeConfigurationError("Tipo de filtro não suportado")
        return f"{self.field} {self.operator} {value}"


class GvcollegeWebAPIClient:
    """Cliente assíncrono read-only; não oferece métodos de escrita."""

    @classmethod
    async def for_tenant(
        cls,
        db: AsyncSession,
        *,
        tenant_id: str,
        config: GvcollegeInstitutionConfig,
        auth_headers: Mapping[str, str] | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> "GvcollegeWebAPIClient":
        if config.tenant_id != tenant_id:
            raise GvcollegeConfigurationError("Tenant da configuração não corresponde ao tenant autenticado.")
        approved_url = await authorize_tenant_destination(
            db, tenant_id=tenant_id, connector_key="gvcollege", url=config.base_url
        )
        approved_host = urlsplit(approved_url).hostname
        trusted_config = replace(
            config, base_url=approved_url, allowed_hosts=frozenset({approved_host})
        )
        return cls(trusted_config, auth_headers=auth_headers, transport=transport, _destination_authorization=_destination_authorization_token())

    def __init__(
        self,
        config: GvcollegeInstitutionConfig,
        *,
        auth_headers: Mapping[str, str] | None = None,
        _destination_authorization: object | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        require_destination_authorization(_destination_authorization)
        self.config = config
        self._auth_headers = dict(auth_headers or {})
        forbidden_headers = {
            "host", "content-length", "transfer-encoding", "connection",
            "proxy-authorization", "proxy-authenticate",
        }
        for key, value in self._auth_headers.items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise GvcollegeConfigurationError("Headers de autenticação devem ser texto")
            if (
                not _HEADER_NAME.fullmatch(key)
                or key.lower() in forbidden_headers
                or any(char in key + value for char in "\r\n")
            ):
                raise GvcollegeConfigurationError("Header de autenticação inválido")
        self._client = httpx.AsyncClient(
            base_url=config.base_url,
            timeout=httpx.Timeout(config.timeout_seconds),
            follow_redirects=False,
            transport=transport,
            headers={"Accept": "application/json", **self._auth_headers},
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "GvcollegeWebAPIClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    def _contract(self, view_key: str) -> GvcollegeViewContract:
        contract = self.config.views.get(view_key)
        if contract is None:
            raise GvcollegeConfigurationError(
                f"View '{view_key}' não homologada para este tenant"
            )
        return contract

    async def fetch_page(
        self,
        view_key: str,
        *,
        order_by: str | None = None,
        select: Sequence[str] | None = None,
        skip: int = 0,
        top: int | None = None,
        filters: Sequence[ODataFilter] = (),
    ) -> list[dict[str, Any]]:
        contract = self._contract(view_key)
        ordering = order_by or contract.default_order_by
        if ordering != contract.pagination_key:
            raise GvcollegeConfigurationError(
                "$orderby deve usar a chave única de paginação homologada"
            )
        if skip < 0:
            raise GvcollegeConfigurationError("$skip não pode ser negativo")
        page_size = self.config.page_size if top is None else top
        if not 1 <= page_size <= 1000:
            raise GvcollegeConfigurationError("$top deve estar entre 1 e 1000")
        selected = tuple(select) if select is not None else contract.source_fields
        if not selected or any(name not in contract.source_fields for name in selected):
            raise GvcollegeConfigurationError("$select contém campo fora do contrato")

        params: list[tuple[str, str]] = [
            ("$orderby", ordering),
            ("$select", ",".join(selected)),
            ("$skip", str(skip)),
            ("$top", str(page_size)),
        ]
        if filters:
            rendered = [item.render(contract) for item in filters]
            params.append(("$filter", " and ".join(rendered)))

        path = f"/api/views/{quote(contract.view_name, safe='')}"
        try:
            async with self._client.stream("GET", path, params=params) as response:
                if response.is_redirect:
                    raise GvcollegeAPIError("Redirecionamento HTTP bloqueado")
                response.raise_for_status()
                chunks: list[bytes] = []
                size = 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > self.config.max_response_bytes:
                        raise GvcollegeAPIError("Resposta excede limite configurado")
                    chunks.append(chunk)
        except httpx.HTTPStatusError as exc:
            raise GvcollegeAPIError(
                f"WebAPI retornou HTTP {exc.response.status_code}"
            ) from exc
        except httpx.HTTPError as exc:
            raise GvcollegeAPIError("Falha de transporte na WebAPI GVcollege") from exc

        try:
            payload = json.loads(b"".join(chunks).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GvcollegeAPIError("Resposta não é JSON UTF-8 válido") from exc
        if isinstance(payload, list):
            rows = payload
        elif isinstance(payload, dict) and isinstance(payload.get("value"), list):
            rows = payload["value"]
        else:
            raise GvcollegeAPIError("Formato de resposta não documentado/inesperado")
        if any(not isinstance(row, dict) for row in rows):
            raise GvcollegeAPIError("A resposta contém registros que não são objetos")
        return rows

    async def iter_pages(
        self,
        view_key: str,
        *,
        order_by: str | None = None,
        select: Sequence[str] | None = None,
        filters: Sequence[ODataFilter] = (),
        max_pages: int = 1000,
    ) -> AsyncIterator[list[dict[str, Any]]]:
        if max_pages < 1:
            raise GvcollegeConfigurationError("max_pages deve ser positivo")
        contract = self._contract(view_key)
        ordering = order_by or contract.default_order_by
        if ordering != contract.pagination_key:
            raise GvcollegeConfigurationError(
                "Paginação exige $orderby pela chave única homologada"
            )
        skip = 0
        for _ in range(max_pages):
            rows = await self.fetch_page(
                view_key, order_by=ordering, select=select, skip=skip,
                top=self.config.page_size, filters=filters,
            )
            if not rows:
                return
            yield rows
            skip += len(rows)
            if len(rows) < self.config.page_size:
                return
        raise GvcollegeAPIError("Paginação excedeu max_pages; interrompida")
