"""Cliente SOAP estritamente limitado ao método TOTVS ReadRecord.

ReadRecord é uma operação de leitura do DataServer. O cliente não expõe
métodos genéricos de POST nem permite escolher operações SOAP arbitrárias.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from sqlalchemy.ext.asyncio import AsyncSession
from xml.etree import ElementTree as ET

import httpx

from app.services.connectors.transport import (
    ConnectorConfigurationError,
    ConnectorTransportError,
    ERPRequestContext,
)
from app.services.connectors.tenant_destinations import (
    _destination_authorization_token,
    authorize_tenant_destination,
    require_destination_authorization,
)


SOAP_ENV = "http://schemas.xmlsoap.org/soap/envelope/"
TOTVS_NS = "http://www.totvs.com/"
READ_RECORD_ACTION = "http://www.totvs.com/IwsDataServer/ReadRecord"
MAX_SOAP_RESPONSE_BYTES = 5 * 1024 * 1024


def _context_string(context: ERPRequestContext) -> str:
    fields = context.as_headers()
    if not fields:
        raise ConnectorConfigurationError("Contexto TOTVS é obrigatório para ReadRecord.")
    return ";".join(f"{key}={value}" for key, value in fields.items())


class TotvsReadOnlySoapClient:
    """Cliente SOAP 1.1 que permite somente DataServer ReadRecord."""

    @classmethod
    async def for_tenant(
        cls,
        db: AsyncSession,
        *,
        tenant_id: str,
        endpoint: str,
        username: str,
        password: str,
        context: ERPRequestContext,
        timeout_seconds: float = 20.0,
        allow_insecure_http: bool = False,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> "TotvsReadOnlySoapClient":
        approved = await authorize_tenant_destination(
            db, tenant_id=tenant_id, connector_key="totvs_rm_soap", url=endpoint
        )
        return cls(
            endpoint=approved, username=username, password=password,
            context=context, timeout_seconds=timeout_seconds,
            allow_insecure_http=allow_insecure_http, transport=transport,
            _destination_authorization=_destination_authorization_token(),
            _destination_authorization=_destination_authorization_token(),
        )

    def __init__(
        self,
        *,
        endpoint: str,
        username: str,
        password: str,
        context: ERPRequestContext,
        timeout_seconds: float = 20.0,
        allow_insecure_http: bool = False,
        transport: httpx.AsyncBaseTransport | None = None,
        _destination_authorization: object | None = None,
    ) -> None:
        require_destination_authorization(_destination_authorization)
        parsed = urlsplit(endpoint)
        if parsed.scheme not in {"https", "http"} or not parsed.netloc:
            raise ConnectorConfigurationError("Endpoint SOAP deve usar HTTP ou HTTPS.")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ConnectorConfigurationError("Endpoint SOAP não pode conter credenciais, query ou fragmento.")
        if parsed.scheme == "http" and not allow_insecure_http:
            raise ConnectorConfigurationError("SOAP sem TLS exige allow_insecure_http explícito.")
        if not username or not password:
            raise ConnectorConfigurationError("Credenciais SOAP são obrigatórias.")
        if timeout_seconds <= 0:
            raise ConnectorConfigurationError("Timeout deve ser maior que zero.")

        self._context = _context_string(context)
        self._client = httpx.AsyncClient(
            auth=httpx.BasicAuth(username, password),
            timeout=httpx.Timeout(timeout_seconds),
            follow_redirects=False,
            transport=transport,
            headers={
                "Content-Type": "text/xml; charset=utf-8",
                "Accept": "text/xml",
                "SOAPAction": f'"{READ_RECORD_ACTION}"',
                "User-Agent": "MIRA-ERP-Connector/1.0",
            },
        )
        self._endpoint = endpoint

    @staticmethod
    def _build_envelope(dataserver: str, primary_key: str, context: str) -> bytes:
        if not dataserver or len(dataserver) > 128 or any(ord(c) < 32 for c in dataserver):
            raise ConnectorConfigurationError("DataServer inválido.")
        if not primary_key or len(primary_key) > 2048 or any(ord(c) < 32 for c in primary_key):
            raise ConnectorConfigurationError("Chave primária inválida.")

        envelope = ET.Element(f"{{{SOAP_ENV}}}Envelope")
        body = ET.SubElement(envelope, f"{{{SOAP_ENV}}}Body")
        operation = ET.SubElement(body, f"{{{TOTVS_NS}}}ReadRecord")
        ET.SubElement(operation, f"{{{TOTVS_NS}}}DataServerName").text = dataserver
        ET.SubElement(operation, f"{{{TOTVS_NS}}}PrimaryKey").text = primary_key
        ET.SubElement(operation, f"{{{TOTVS_NS}}}Contexto").text = context
        return ET.tostring(envelope, encoding="utf-8", xml_declaration=True)

    async def read_record(self, *, dataserver: str, primary_key: str) -> str:
        """Executa apenas ReadRecord e retorna o XML serializado pelo DataServer."""
        payload = self._build_envelope(dataserver, primary_key, self._context)
        try:
            response = await self._client.post(self._endpoint, content=payload)
        except httpx.RequestError:
            raise ConnectorTransportError("Falha de comunicação com o serviço SOAP TOTVS.") from None

        if len(response.content) > MAX_SOAP_RESPONSE_BYTES:
            raise ConnectorTransportError("Resposta SOAP excede o tamanho máximo permitido.")

        # Redirects are disabled; reject them before attempting to parse an HTML
        # redirect page as a SOAP envelope.
        if 300 <= response.status_code < 400:
            raise ConnectorTransportError(
                f"Serviço SOAP respondeu com HTTP {response.status_code}."
            )

        try:
            root = ET.fromstring(response.content)
        except ET.ParseError:
            if response.status_code >= 400:
                raise ConnectorTransportError(
                    f"Serviço SOAP respondeu com HTTP {response.status_code}."
                ) from None
            raise ConnectorTransportError("Serviço SOAP retornou XML inválido.") from None

        fault = root.find(f".//{{{SOAP_ENV}}}Fault")
        if fault is not None:
            fault_string = fault.findtext("faultstring") or "Falha SOAP"
            safe_fault = " ".join(fault_string.split())[:240]
            raise ConnectorTransportError(f"Falha SOAP ReadRecord: {safe_fault}")

        if response.status_code >= 400:
            raise ConnectorTransportError(
                f"Serviço SOAP respondeu com HTTP {response.status_code}."
            )

        result = root.find(f".//{{{TOTVS_NS}}}ReadRecordResult")
        if result is None:
            raise ConnectorTransportError("Resposta SOAP não contém ReadRecordResult.")
        return result.text or ET.tostring(result, encoding="unicode")

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "TotvsReadOnlySoapClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()
