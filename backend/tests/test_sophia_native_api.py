"""Contract tests for the read-only SophiA Gestão Escolar Web API v1 client."""
import json
import math

import httpx
import pytest

from app.services.connectors.sophia_api import (
    READ_ENDPOINTS,
    SophiaApiClient,
    SophiaApiConfig,
    SophiaAuthenticationError,
    SophiaContractError,
)


def config(**overrides):
    values = {
        "base_url": "https://sophia.example/6150/api/v1",
        "username": "mira-integration",
        "password": "test-secret",
    }
    values.update(overrides)
    return SophiaApiConfig(**values)


@pytest.mark.asyncio
async def test_authenticates_then_reads_units_with_token_header():
    seen = []

    async def handler(request: httpx.Request):
        seen.append(request)
        if request.url.path.endswith("/Autenticacao/PostAutenticacao"):
            assert json.loads(request.content) == {
                "Usuario": "mira-integration",
                "Senha": "test-secret",
            }
            return httpx.Response(200, json="issued-token")
        assert request.headers["Token"] == "issued-token"
        assert request.headers["Accept"] == "application/json"
        return httpx.Response(200, json=[{"Codigo": 1, "Descricao": "Unidade Centro"}])

    client = SophiaApiClient(config(), transport=httpx.MockTransport(handler))
    try:
        result = await client.get_units()
    finally:
        await client.close()

    assert result == [{"Codigo": 1, "Descricao": "Unidade Centro"}]
    assert len(seen) == 2
    assert seen[1].url.path.endswith(READ_ENDPOINTS["units"])


@pytest.mark.asyncio
async def test_finance_query_uses_documented_codigo_parameter():
    requests = []

    async def handler(request: httpx.Request):
        requests.append(request)
        if request.url.path.endswith("/Autenticacao/PostAutenticacao"):
            return httpx.Response(200, json="token")
        return httpx.Response(200, json=[{"Pago": False, "ValorPrevisto": 500.0, "ValorPago": 0.0}])

    client = SophiaApiClient(config(), transport=httpx.MockTransport(handler))
    try:
        result = await client.get_student_finance("123")
    finally:
        await client.close()

    assert result[0]["Pago"] is False
    assert requests[1].url.params["codigo"] == "123"


@pytest.mark.asyncio
async def test_reauthenticates_once_after_expired_token():
    auth_count = 0
    data_count = 0

    async def handler(request: httpx.Request):
        nonlocal auth_count, data_count
        if request.url.path.endswith("/Autenticacao/PostAutenticacao"):
            auth_count += 1
            return httpx.Response(200, json=f"token-{auth_count}")
        data_count += 1
        if data_count == 1:
            return httpx.Response(401)
        assert request.headers["Token"] == "token-2"
        return httpx.Response(200, json=[])

    client = SophiaApiClient(config(), transport=httpx.MockTransport(handler))
    try:
        assert await client.get_courses() == []
    finally:
        await client.close()

    assert auth_count == 2
    assert data_count == 2


@pytest.mark.asyncio
async def test_rejects_invalid_credentials_and_non_array_payloads():
    async def unauthorized(_: httpx.Request):
        return httpx.Response(401)

    client = SophiaApiClient(config(), transport=httpx.MockTransport(unauthorized))
    with pytest.raises(SophiaAuthenticationError):
        await client.get_units()
    await client.close()

    async def invalid_payload(request: httpx.Request):
        if request.url.path.endswith("/Autenticacao/PostAutenticacao"):
            return httpx.Response(200, json="token")
        return httpx.Response(200, json={"items": []})

    client = SophiaApiClient(config(), transport=httpx.MockTransport(invalid_payload))
    with pytest.raises(SophiaContractError):
        await client.get_courses()
    await client.close()


@pytest.mark.parametrize("timeout", [0, -1, math.nan, math.inf, -math.inf])
def test_sophia_config_rejects_non_positive_or_non_finite_timeouts(timeout):
    with pytest.raises(ValueError, match="positive and finite"):
        SophiaApiClient(config(timeout_seconds=timeout))


@pytest.mark.parametrize(
    "base_url",
    [
        "http://sophia.example/6150/api/v1",
        "https://user:pass@sophia.example/6150/api/v1",
        "https://sophia.example/6150/api/v2",
        "https://sophia.example/6150/api/v1?tenant=other",
        "https://127.0.0.1/6150/api/v1",
        "https://service.local/6150/api/v1",
        "https://sophia.example/../v1",
    ],
)
def test_rejects_unsafe_or_unverified_base_urls(base_url):
    with pytest.raises(ValueError):
        SophiaApiClient(config(base_url=base_url))

@pytest.mark.asyncio
async def test_boleto_uses_documented_id_titulo_parameter():
    requests = []

    async def handler(request: httpx.Request):
        requests.append(request)
        if request.url.path.endswith("/Autenticacao/PostAutenticacao"):
            return httpx.Response(200, json="token")
        return httpx.Response(200, json={"CaminhoPDF": "https://example.invalid/boleto", "LinhaDigitavel": "00190"})

    client = SophiaApiClient(config(), transport=httpx.MockTransport(handler))
    try:
        result = await client.get_student_boleto(987)
    finally:
        await client.close()

    assert result["LinhaDigitavel"] == "00190"
    assert requests[1].url.params["idTitulo"] == "987"




def test_sophia_config_repr_does_not_expose_credentials():
    value = config(username="secret-user", password="secret-password")
    rendered = repr(value)
    assert "secret-user" not in rendered
    assert "secret-password" not in rendered
