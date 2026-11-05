from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.services.connectors.omie_api import (
    OmieApiClient,
    OmieApiError,
    OmieCredentials,
)


def _credentials(*, expires_at=None):
    return OmieCredentials(
        app_hash="app-hash-demo",
        access_token="access-token-abcdefghijklmnop",
        refresh_token="refresh-token-abcdefghijklmnop",
        expires_at=expires_at or (datetime.now(timezone.utc) + timedelta(hours=12)),
    )


@pytest.mark.asyncio
async def test_list_accounts_receivable_uses_post_bearer_and_allowlisted_call():
    seen = {}

    async def handler(request: httpx.Request):
        seen["method"] = request.method
        seen["url"] = str(request.url)
        seen["authorization"] = request.headers.get("Authorization")
        seen["body"] = __import__("json").loads(request.content)
        return httpx.Response(200, json={"pagina": 2, "conta_receber_cadastro": []})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = OmieApiClient(_credentials(), http_client=http)
    try:
        result = await client.list_accounts_receivable(page=2, page_size=25)
    finally:
        await client.close()
        await http.aclose()

    assert result["pagina"] == 2
    assert seen["method"] == "POST"
    assert seen["url"] == "https://app.omie.com.br/api/v1/financas/contareceber/"
    assert seen["authorization"] == "Bearer access-token-abcdefghijklmnop"
    assert seen["body"] == {
        "call": "ListarContasReceber",
        "param": [{"pagina": 2, "registros_por_pagina": 25}],
    }


@pytest.mark.asyncio
async def test_expired_access_token_is_refreshed_and_rotated_before_read():
    calls = []

    async def handler(request: httpx.Request):
        calls.append((request.method, str(request.url), request.headers.get("Authorization")))
        if "refresh-token" in str(request.url):
            assert request.headers.get("Authorization") is None
            return httpx.Response(200, json={
                "token": "new-access-token-abcdefghijklmnop",
                "refresh_token": "new-refresh-token-abcdefghijklmnop",
            })
        return httpx.Response(200, json={"pagina": 1, "conta_receber_cadastro": []})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    creds = _credentials(expires_at=datetime.now(timezone.utc) - timedelta(minutes=1))
    client = OmieApiClient(creds, http_client=http)
    try:
        await client.list_accounts_receivable()
    finally:
        await client.close()
        await http.aclose()

    assert len(calls) == 2
    assert calls[0][1] == "https://app.omie.com.br/api/portal/apps/app-hash-demo/refresh-token/"
    assert calls[1][2] == "Bearer new-access-token-abcdefghijklmnop"
    assert creds.refresh_token == "new-refresh-token-abcdefghijklmnop"
    assert creds.expires_at > datetime.now(timezone.utc) + timedelta(hours=23)


@pytest.mark.asyncio
async def test_retryable_omie_rate_limit_is_classified_without_leaking_response():
    async def handler(_request: httpx.Request):
        return httpx.Response(429, text="private upstream detail")

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = OmieApiClient(_credentials(), http_client=http)
    try:
        with pytest.raises(OmieApiError) as exc:
            await client.list_accounts_payable()
    finally:
        await client.close()
        await http.aclose()

    assert exc.value.code == "http_429"
    assert exc.value.retryable is True
    assert "private upstream detail" not in str(exc.value)


@pytest.mark.asyncio
async def test_api_business_error_is_not_returned_as_financial_data():
    async def handler(_request: httpx.Request):
        return httpx.Response(200, json={"faultcode": "SOAP-ENV:Client", "faultstring": "invalid operation"})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = OmieApiClient(_credentials(), http_client=http)
    try:
        with pytest.raises(OmieApiError) as exc:
            await client.list_accounts_payable()
    finally:
        await client.close()
        await http.aclose()

    assert exc.value.code == "omie_business_error"
