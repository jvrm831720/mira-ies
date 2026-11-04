from __future__ import annotations

import json

import httpx
import pytest

from app.services.connectors.gvcollege_api import (
    GvcollegeAPIError,
    GvcollegeConfigurationError,
    GvcollegeInstitutionConfig,
    GvcollegeViewContract,
    GvcollegeWebAPIClient,
    ODataFilter,
)


def make_config(**overrides):
    values = {
        "tenant_id": "tenant-a",
        "base_url": "https://erp.instituicao.edu.br",
        "allowed_hosts": frozenset({"erp.instituicao.edu.br"}),
        "views": {
            "pessoa": GvcollegeViewContract(
                view_name="Pessoa",
                source_fields=("codigo", "nome", "email"),
                pagination_key="codigo",
                field_mapping={"matricula": "codigo", "nome": "nome"},
                default_order_by="codigo",
            )
        },
        "page_size": 2,
    }
    values.update(overrides)
    return GvcollegeInstitutionConfig(**values)


@pytest.mark.asyncio
async def test_fetch_page_uses_contract_and_limited_odata_query():
    seen = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["request"] = request
        return httpx.Response(200, json=[{"codigo": 10, "nome": "Ana"}])

    client = GvcollegeWebAPIClient(
        make_config(),
        auth_headers={"Authorization": "Bearer tenant-secret"},
        transport=httpx.MockTransport(handler),
    )
    try:
        rows = await client.fetch_page(
            "pessoa",
            select=("codigo", "nome"),
            filters=(ODataFilter("nome", "eq", "O'Brien"),),
        )
        assert rows == [{"codigo": 10, "nome": "Ana"}]
        request = seen["request"]
        assert request.method == "GET"
        assert request.url.path == "/api/views/Pessoa"
        assert request.url.params["$orderby"] == "codigo"
        assert request.url.params["$select"] == "codigo,nome"
        assert request.url.params["$skip"] == "0"
        assert request.url.params["$top"] == "2"
        assert request.url.params["$filter"] == "nome eq 'O''Brien'"
        assert request.headers["Authorization"] == "Bearer tenant-secret"
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_iter_pages_uses_offset_and_stops_on_short_page():
    calls = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(int(request.url.params["$skip"]))
        if len(calls) == 1:
            return httpx.Response(200, json=[{"codigo": 1}, {"codigo": 2}])
        return httpx.Response(200, json=[{"codigo": 3}])

    client = GvcollegeWebAPIClient(make_config(), transport=httpx.MockTransport(handler))
    try:
        pages = [page async for page in client.iter_pages("pessoa")]
        assert [len(page) for page in pages] == [2, 1]
        assert calls == [0, 2]
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_accepts_documented_odata_value_envelope():
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"value": [{"codigo": 4}]})

    client = GvcollegeWebAPIClient(make_config(), transport=httpx.MockTransport(handler))
    try:
        assert await client.fetch_page("pessoa") == [{"codigo": 4}]
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_redirects_are_rejected():
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": "https://evil.example/"})

    client = GvcollegeWebAPIClient(make_config(), transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(GvcollegeAPIError, match="Redirecionamento"):
            await client.fetch_page("pessoa")
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_response_size_limit_is_enforced():
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=json.dumps([{"nome": "x" * 500}]).encode())

    client = GvcollegeWebAPIClient(
        make_config(max_response_bytes=32),
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(GvcollegeAPIError, match="limite"):
            await client.fetch_page("pessoa")
    finally:
        await client.aclose()


def test_configuration_rejects_http_and_unapproved_host():
    with pytest.raises(GvcollegeConfigurationError):
        make_config(base_url="http://erp.instituicao.edu.br")
    with pytest.raises(GvcollegeConfigurationError):
        make_config(base_url="https://other.example")


def test_configuration_rejects_private_ip_and_invalid_page_size():
    with pytest.raises(GvcollegeConfigurationError):
        make_config(base_url="https://127.0.0.1", allowed_hosts=frozenset({"127.0.0.1"}))
    with pytest.raises(GvcollegeConfigurationError):
        make_config(page_size=1001)


def test_view_and_field_contract_is_explicit():
    with pytest.raises(GvcollegeConfigurationError):
        GvcollegeViewContract("dbo.GVMVW_Pessoa", ("codigo",), pagination_key="codigo")
    with pytest.raises(GvcollegeConfigurationError):
        GvcollegeViewContract("Pessoa", ("codigo",), pagination_key="codigo", default_order_by="nome")


@pytest.mark.asyncio
async def test_rejects_uncontracted_view_fields_and_raw_filter_operator():
    client = GvcollegeWebAPIClient(make_config(), transport=httpx.MockTransport(
        lambda _: httpx.Response(200, json=[])
    ))
    try:
        with pytest.raises(GvcollegeConfigurationError):
            await client.fetch_page("financeiro")
        with pytest.raises(GvcollegeConfigurationError):
            await client.fetch_page("pessoa", select=("senha",))
        with pytest.raises(GvcollegeConfigurationError):
            await client.fetch_page(
                "pessoa", filters=(ODataFilter("nome", "contains", "Ana"),)
            )
    finally:
        await client.aclose()


def test_auth_headers_cannot_override_transport_routing():
    for header in ("Host", "Content-Length", "Transfer-Encoding", "Connection"):
        with pytest.raises(GvcollegeConfigurationError):
            GvcollegeWebAPIClient(make_config(), auth_headers={header: "attacker.example"})


def test_auth_headers_reject_non_text_values_and_line_breaks():
    with pytest.raises(GvcollegeConfigurationError):
        GvcollegeWebAPIClient(make_config(), auth_headers={"Authorization": "Bearer x" + chr(13) + chr(10) + "Host: evil"})
    with pytest.raises(GvcollegeConfigurationError):
        GvcollegeWebAPIClient(make_config(), auth_headers={"Authorization": 123})


def test_odata_filter_rejects_non_finite_numeric_values():
    contract = make_config().views["pessoa"]
    for value in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(GvcollegeConfigurationError, match="finito"):
            ODataFilter("codigo", "eq", value).render(contract)


def test_configuration_rejects_unapproved_port_and_path_prefix():
    with pytest.raises(GvcollegeConfigurationError):
        make_config(base_url="https://erp.instituicao.edu.br:8443")
    with pytest.raises(GvcollegeConfigurationError):
        make_config(base_url="https://erp.instituicao.edu.br/custom-prefix")


def test_configuration_rejects_non_finite_timeout_and_invalid_response_limit():
    with pytest.raises(GvcollegeConfigurationError):
        make_config(timeout_seconds=float("nan"))
    with pytest.raises(GvcollegeConfigurationError):
        make_config(max_response_bytes=True)


def test_auth_header_name_must_follow_http_token_syntax():
    with pytest.raises(GvcollegeConfigurationError):
        GvcollegeWebAPIClient(make_config(), auth_headers={"Bad Header": "value"})
