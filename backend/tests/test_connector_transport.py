"""Testes puros do contrato de transporte ERP (sem rede ou banco)."""

import math

import httpx
import pytest

from app.services.connectors.transport import (
    ConnectorConfigurationError,
    ConnectorTransportError,
    ERPRequestContext,
    ReadOnlyRestClient,
)


@pytest.mark.asyncio
async def test_rest_client_sends_get_basic_auth_and_totvs_context():
    seen = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"items": [{"RA": "000123"}]})

    client = ReadOnlyRestClient(
        base_url="https://rm.example.test:8051/rmsrestdataserver/rest",
        username="integration-user",
        password="secret-value",
        context=ERPRequestContext(
            codcoligada="1", codfilial="2", codtipocurso="1", codsistema="S"
        ),
        transport=httpx.MockTransport(handler),
    )
    try:
        payload = await client.get_json("EduParcelaData", params={"start": 0, "limit": 10})
    finally:
        await client.aclose()

    request = seen[0]
    assert request.method == "GET"
    assert request.url.path.endswith("/EduParcelaData")
    assert dict(request.url.params) == {"start": "0", "limit": "10"}
    assert request.headers["CODCOLIGADA"] == "1"
    assert request.headers["CODFILIAL"] == "2"
    assert request.headers["CODTIPOCURSO"] == "1"
    assert request.headers["CODSISTEMA"] == "S"
    assert request.headers["authorization"].startswith("Basic ")
    assert payload == {"items": [{"RA": "000123"}]}


@pytest.mark.asyncio
async def test_offset_pagination_uses_explicit_items_key_and_stops_on_short_page():
    offsets = []

    async def handler(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params["start"])
        offsets.append(offset)
        data = [{"id": offset + 1}, {"id": offset + 2}] if offset == 0 else [{"id": 3}]
        return httpx.Response(200, json={"records": data})

    client = ReadOnlyRestClient(
        base_url="https://rm.example.test",
        transport=httpx.MockTransport(handler),
    )
    try:
        pages = [
            page async for page in client.iter_offset_pages(
                "EduParcelaData", items_key="records", page_size=2
            )
        ]
    finally:
        await client.aclose()

    assert offsets == [0, 2]
    assert pages == [[{"id": 1}, {"id": 2}], [{"id": 3}]]


@pytest.mark.asyncio
async def test_pagination_limit_fails_instead_of_silently_truncating():
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[{"id": 1}])

    client = ReadOnlyRestClient(
        base_url="https://rm.example.test",
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(ConnectorTransportError, match="Limite de páginas"):
            _ = [
                page async for page in client.iter_offset_pages(
                    "records", items_key="unused", page_size=1, max_pages=2
                )
            ]
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_rest_client_does_not_follow_redirects():
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": "https://other.example.test/collect"})

    client = ReadOnlyRestClient(
        base_url="https://rm.example.test",
        username="user",
        password="password",
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(ConnectorTransportError, match="HTTP 302"):
            await client.get_json("students")
    finally:
        await client.aclose()


@pytest.mark.parametrize(
    "base_url",
    [
        "http://rm.example.test",
        "https://user:password@rm.example.test",
        "https://rm.example.test?tenant=other",
        "file:///etc/passwd",
    ],
)
def test_unsafe_base_urls_are_rejected(base_url):
    with pytest.raises(ConnectorConfigurationError):
        ReadOnlyRestClient(base_url=base_url)


@pytest.mark.asyncio
async def test_absolute_and_traversal_paths_are_rejected():
    client = ReadOnlyRestClient(base_url="https://rm.example.test")
    try:
        with pytest.raises(ConnectorConfigurationError):
            await client.get_json("https://attacker.example.test/steal")
        with pytest.raises(ConnectorConfigurationError):
            await client.get_json("../other-tenant")
    finally:
        await client.aclose()


@pytest.mark.parametrize("timeout", [0, -1, math.nan, math.inf, -math.inf])
def test_rest_client_rejects_non_positive_or_non_finite_timeouts(timeout):
    with pytest.raises(ConnectorConfigurationError, match="positivo e finito"):
        ReadOnlyRestClient(base_url="https://rm.example.test", timeout_seconds=timeout)


def test_context_rejects_header_injection():
    with pytest.raises(ConnectorConfigurationError):
        ERPRequestContext(codcoligada="1\r\nAuthorization: Bearer stolen").as_headers()


def test_http_requires_explicit_opt_in_for_private_network_deployments():
    client = ReadOnlyRestClient(base_url="http://127.0.0.1:8051", allow_insecure_http=True)
    assert client is not None


@pytest.mark.asyncio
async def test_offset_pagination_supports_fixed_query_params_and_raw_list_response():
    requests = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        offset = int(request.url.params["start"])
        records = [{"RA": "000001"}, {"RA": "000002"}] if offset == 0 else []
        return httpx.Response(200, json=records)

    client = ReadOnlyRestClient(
        base_url="https://rm.example.test/rmsrestdataserver/rest",
        transport=httpx.MockTransport(handler),
    )
    try:
        pages = [
            page
            async for page in client.iter_offset_pages(
                "EduAlunoData",
                items_key="",
                page_size=2,
                query_params={"filter": '["CODCOLIGADA =:CODCOLIGADA","3"]'},
            )
        ]
    finally:
        await client.aclose()

    assert len(pages) == 1
    assert [row["RA"] for row in pages[0]] == ["000001", "000002"]
    assert dict(requests[0].url.params) == {
        "start": "0",
        "limit": "2",
        "filter": '["CODCOLIGADA =:CODCOLIGADA","3"]',
    }


@pytest.mark.asyncio
async def test_offset_pagination_rejects_reserved_query_params():
    client = ReadOnlyRestClient(base_url="https://rm.example.test")
    try:
        with pytest.raises(ConnectorConfigurationError, match="reservados"):
            _ = [
                page
                async for page in client.iter_offset_pages(
                    "EduAlunoData",
                    items_key="",
                    query_params={"start": 999},
                )
            ]
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_rest_for_tenant_uses_persisted_destination(monkeypatch):
    async def authorize(db, *, tenant_id, connector_key, url):
        assert tenant_id == "tenant-a"
        assert connector_key == "rest"
        assert url == "https://untrusted-config.example"
        return "https://approved.example"

    monkeypatch.setattr(
        "app.services.connectors.transport.authorize_tenant_destination", authorize
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "approved.example"
        return httpx.Response(200, json={"ok": True})

    client = await ReadOnlyRestClient.for_tenant(
        object(),
        tenant_id="tenant-a",
        base_url="https://untrusted-config.example",
        transport=httpx.MockTransport(handler),
    )
    try:
        assert await client.get_json("health") == {"ok": True}
    finally:
        await client.aclose()
