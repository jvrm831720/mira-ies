"""Adapter inicial TOTVS RM: leituras explícitas, sem inferência de domínio.

Este adapter não transforma dados financeiros/acadêmicos em features canônicas.
Os payloads permanecem brutos até que a instituição homologue a semântica.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from xml.etree import ElementTree

from app.services.connectors.soap import TotvsReadOnlySoapClient
from app.services.connectors.transport import ERPRequestContext, ReadOnlyRestClient
from app.services.connectors.tenant_destinations import (
    authorize_connector_client,
    require_destination_authorization,
)


@dataclass(frozen=True, slots=True)
class TotvsRMConfig:
    rest_base_url: str
    soap_endpoint: str
    username: str = field(repr=False)
    password: str = field(repr=False)
    context: ERPRequestContext
    allow_insecure_http: bool = False
    timeout_seconds: float = 20.0

    def __post_init__(self) -> None:
        if not self.context.codcoligada:
            raise ValueError("CODCOLIGADA é obrigatório na configuração do RM.")


class TotvsRMReadOnlyAdapter:
    """Operações de leitura RM sem sincronização automática ou escrita."""

    @classmethod
    async def for_tenant(
        cls, db, *, tenant_id: str, config: TotvsRMConfig
    ) -> "TotvsRMReadOnlyAdapter":
        await authorize_connector_client(
            db, tenant_id=tenant_id, connector_key="totvs_rm", url=config.soap_endpoint
        )
        token = await authorize_connector_client(
            db, tenant_id=tenant_id, connector_key="totvs_rm", url=config.rest_base_url
        )
        return cls(config, authorization_token=token)

    def __init__(
        self, config: TotvsRMConfig, *, authorization_token: object | None = None
    ) -> None:
        require_destination_authorization(authorization_token)
        self._config = config
        self._authorization_token = authorization_token

    async def read_student_record(self, *, ra: str) -> dict[str, str]:
        """Lê aluno por chave composta e retorna apenas CODCOLIGADA/RA.

        O XML bruto do EduAlunoData pode conter dados pessoais e sensíveis.
        O adapter descarta todos os campos fora da allowlist mínima.
        """
        normalized_ra = str(ra).strip()
        if not normalized_ra or any(ord(char) < 32 for char in normalized_ra):
            raise ValueError("RA inválido.")
        async with TotvsReadOnlySoapClient(
            endpoint=self._config.soap_endpoint,
            username=self._config.username,
            password=self._config.password,
            context=self._config.context,
            timeout_seconds=self._config.timeout_seconds,
            allow_insecure_http=self._config.allow_insecure_http,
            authorization_token=self._authorization_token,
        ) as soap:
            raw_xml = await soap.read_record(
                dataserver="EduAlunoData",
                primary_key=f"{self._config.context.codcoligada};{normalized_ra}",
            )

        try:
            root = ElementTree.fromstring(raw_xml)
        except ElementTree.ParseError:
            raise ValueError("EduAlunoData retornou XML inválido.") from None

        coligada_node = root.find(".//CODCOLIGADA")
        ra_node = root.find(".//RA")
        coligada = self._config.context.codcoligada.strip()
        if coligada_node is None or (coligada_node.text or "").strip() != coligada:
            raise ValueError("ReadRecord retornou aluno fora da CODCOLIGADA solicitada.")
        if ra_node is None or (ra_node.text or "").strip() != normalized_ra:
            raise ValueError("ReadRecord retornou RA diferente do solicitado.")
        return {"CODCOLIGADA": coligada, "RA": normalized_ra}

    async def iter_student_keys(
        self,
        *,
        page_size: int = 100,
        max_pages: int = 1000,
        start: int = 0,
    ) -> AsyncIterator[list[dict[str, str]]]:
        """Lista apenas CODCOLIGADA/RA; descarta campos pessoais do payload RM.

        GetAll depende de o DataServer e o usuário estarem habilitados na IES.
        O retorno é uma lista de chaves, não um snapshot consistente do roster.
        """
        coligada = self._config.context.codcoligada
        if coligada is None or not coligada.strip():
            raise ValueError("CODCOLIGADA é obrigatória para listar alunos.")

        filter_expression = json.dumps(
            ["CODCOLIGADA =:CODCOLIGADA", coligada.strip()],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        async with ReadOnlyRestClient(
            base_url=self._config.rest_base_url,
            username=self._config.username,
            password=self._config.password,
            context=self._config.context,
            timeout_seconds=self._config.timeout_seconds,
            allow_insecure_http=self._config.allow_insecure_http,
            authorization_token=self._authorization_token,
        ) as rest:
            async for page in rest.iter_offset_pages(
                "EduAlunoData",
                items_key="",
                page_size=page_size,
                max_pages=max_pages,
                start=start,
                query_params={"filter": filter_expression},
            ):
                safe_page: list[dict[str, str]] = []
                for record in page:
                    if not isinstance(record, dict):
                        raise ValueError("Registro EduAlunoData retornou formato inválido.")
                    record_coligada = record.get("CODCOLIGADA")
                    ra = record.get("RA")
                    if record_coligada is None or str(record_coligada).strip() != coligada.strip():
                        raise ValueError("Registro EduAlunoData fora da CODCOLIGADA solicitada.")
                    if ra is None or not str(ra).strip():
                        raise ValueError("Registro EduAlunoData sem RA; lote interrompido.")
                    safe_page.append(
                        {"CODCOLIGADA": coligada.strip(), "RA": str(ra).strip()}
                    )
                yield safe_page

    async def iter_raw_pages(
        self,
        *,
        path: str,
        items_key: str,
        page_size: int = 100,
        max_pages: int = 1000,
    ) -> AsyncIterator[list[object]]:
        """Lê páginas REST sem mapear status financeiro ou saldo devedor."""
        async with ReadOnlyRestClient(
            base_url=self._config.rest_base_url,
            username=self._config.username,
            password=self._config.password,
            context=self._config.context,
            timeout_seconds=self._config.timeout_seconds,
            allow_insecure_http=self._config.allow_insecure_http,
            authorization_token=self._authorization_token,
        ) as rest:
            async for page in rest.iter_offset_pages(
                path,
                items_key=items_key,
                page_size=page_size,
                max_pages=max_pages,
            ):
                yield page
