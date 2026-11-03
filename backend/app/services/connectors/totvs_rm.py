"""Adapter inicial TOTVS RM: leituras explícitas, sem inferência de domínio.

Este adapter não transforma dados financeiros/acadêmicos em features canônicas.
Os payloads permanecem brutos até que a instituição homologue a semântica.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from app.services.connectors.soap import TotvsReadOnlySoapClient
from app.services.connectors.transport import ERPRequestContext, ReadOnlyRestClient


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

    def __init__(self, config: TotvsRMConfig) -> None:
        self._config = config

    async def read_student_record(self, *, ra: str) -> str:
        """Lê um aluno por chave composta CODCOLIGADA;RA.

        Isto não é uma operação de listagem/roster.
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
        ) as soap:
            return await soap.read_record(
                dataserver="EduAlunoData",
                primary_key=f"{self._config.context.codcoligada};{normalized_ra}",
            )

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
        ) as rest:
            async for page in rest.iter_offset_pages(
                path,
                items_key=items_key,
                page_size=page_size,
                max_pages=max_pages,
            ):
                yield page
