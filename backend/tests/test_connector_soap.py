"""Testes do cliente SOAP TOTVS limitado a ReadRecord."""

import httpx
import pytest
from xml.etree import ElementTree as ET

from app.services.connectors.soap import (
    READ_RECORD_ACTION,
    SOAP_ENV,
    TOTVS_NS,
    TotvsReadOnlySoapClient,
)
from app.services.connectors.transport import (
    ConnectorConfigurationError,
    ConnectorTransportError,
    ERPRequestContext,
)


CTX = ERPRequestContext(codcoligada="1", codfilial="2", codtipocurso="1", codsistema="S")


@pytest.mark.asyncio
async def test_soap_client_posts_only_readrecord_with_totvs_context():
    requests = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        root = ET.Element(f"{{{SOAP_ENV}}}Envelope")
        body = ET.SubElement(root, f"{{{SOAP_ENV}}}Body")
        response = ET.SubElement(body, f"{{{TOTVS_NS}}}ReadRecordResponse")
        ET.SubElement(response, f"{{{TOTVS_NS}}}ReadRecordResult").text = "<Aluno><RA>000123</RA></Aluno>"
        return httpx.Response(200, content=ET.tostring(root))

    client = TotvsReadOnlySoapClient(
        endpoint="https://rm.example.test:8051/wsDataServer/MEX",
        username="readonly",
        password="secret",
        context=CTX,
        transport=httpx.MockTransport(handler),
    )
    try:
        result = await client.read_record(dataserver="EduAlunoData", primary_key="1;000123")
    finally:
        await client.aclose()

    request = requests[0]
    assert request.method == "POST"
    assert request.headers["SOAPAction"] == f'"{READ_RECORD_ACTION}"'
    assert request.headers["authorization"].startswith("Basic ")
    root = ET.fromstring(request.content)
    operation = root.find(f".//{{{TOTVS_NS}}}ReadRecord")
    assert operation is not None
    assert operation.findtext(f"{{{TOTVS_NS}}}DataServerName") == "EduAlunoData"
    assert operation.findtext(f"{{{TOTVS_NS}}}PrimaryKey") == "1;000123"
    assert operation.findtext(f"{{{TOTVS_NS}}}Contexto") == (
        "CODCOLIGADA=1;CODFILIAL=2;CODTIPOCURSO=1;CODSISTEMA=S"
    )
    assert result == "<Aluno><RA>000123</RA></Aluno>"


@pytest.mark.asyncio
async def test_soap_fault_is_reported_without_leaking_request_credentials():
    async def handler(_request: httpx.Request) -> httpx.Response:
        root = ET.Element(f"{{{SOAP_ENV}}}Envelope")
        body = ET.SubElement(root, f"{{{SOAP_ENV}}}Body")
        fault = ET.SubElement(body, f"{{{SOAP_ENV}}}Fault")
        ET.SubElement(fault, "faultstring").text = "Access denied"
        return httpx.Response(500, content=ET.tostring(root))

    client = TotvsReadOnlySoapClient(
        endpoint="https://rm.example.test/service",
        username="secret-user",
        password="secret-password",
        context=CTX,
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(ConnectorTransportError, match="Access denied") as exc:
            await client.read_record(dataserver="EduAlunoData", primary_key="1;123")
        assert "secret-password" not in str(exc.value)
    finally:
        await client.aclose()


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://rm.example.test/service",
        "https://user:pass@rm.example.test/service",
        "https://rm.example.test/service?tenant=other",
    ],
)
def test_soap_endpoint_requires_tls_and_clean_url(endpoint):
    with pytest.raises(ConnectorConfigurationError):
        TotvsReadOnlySoapClient(
            endpoint=endpoint,
            username="user",
            password="pass",
            context=CTX,
        )


@pytest.mark.asyncio
async def test_soap_redirect_is_not_followed():
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": "https://other.example.test/soap"})

    client = TotvsReadOnlySoapClient(
        endpoint="https://rm.example.test/service",
        username="user",
        password="pass",
        context=CTX,
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(ConnectorTransportError, match="HTTP 302"):
            await client.read_record(dataserver="EduAlunoData", primary_key="1;123")
    finally:
        await client.aclose()


def test_soap_envelope_rejects_control_characters_in_identifiers():
    with pytest.raises(ConnectorConfigurationError):
        TotvsReadOnlySoapClient._build_envelope("EduAlunoData", "1\n123", "CODCOLIGADA=1")
