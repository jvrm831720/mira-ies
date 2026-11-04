from __future__ import annotations

import httpx
import pytest

from app.services.connectors.totvs_rm_executor import (
    _assert_executor_contract_enabled, _normalize_roster_record, _read_page, _timeout_seconds,
    _validate_context, _validate_endpoint,
)
from app.services.connectors.totvs_rm_sync_orchestrator import RMJobError, RMTransientJobError


@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf", "-inf", "not-a-number"])
def test_rm_timeout_environment_rejects_invalid_values(monkeypatch, value):
    monkeypatch.setenv("RM_SYNC_CONNECT_TIMEOUT_SECONDS", value)
    with pytest.raises(RMJobError, match="timeout"):
        _timeout_seconds("RM_SYNC_CONNECT_TIMEOUT_SECONDS", "10")


def test_rm_timeout_environment_accepts_positive_finite_value(monkeypatch):
    monkeypatch.setenv("RM_SYNC_CONNECT_TIMEOUT_SECONDS", "3.5")
    assert _timeout_seconds("RM_SYNC_CONNECT_TIMEOUT_SECONDS", "10") == 3.5


def test_endpoint_requires_https_and_explicit_host_allowlist(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("RM_SYNC_ALLOWED_HOSTS", "rm.ies.local")
    assert _validate_endpoint("https://rm.ies.local:8051") == "https://rm.ies.local:8051"
    with pytest.raises(RMJobError, match="HTTPS"):
        _validate_endpoint("http://rm.ies.local:8051")
    with pytest.raises(RMJobError, match="allowlist"):
        _validate_endpoint("https://unlisted.ies.local")


def test_insecure_http_only_allowed_in_development(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("RM_SYNC_ALLOW_INSECURE_HTTP", "true")
    monkeypatch.setenv("RM_SYNC_ALLOWED_HOSTS", "127.0.0.1")
    assert _validate_endpoint("http://127.0.0.1:8051") == "http://127.0.0.1:8051"
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(RMJobError, match="HTTPS"):
        _validate_endpoint("http://127.0.0.1:8051")


def test_context_headers_are_allowlisted_and_coligada_bound():
    assert _validate_context({"CODCOLIGADA": "3", "CODFILIAL": "1"}, "3") == {
        "CODCOLIGADA": "3", "CODFILIAL": "1"
    }
    with pytest.raises(RMJobError, match="CODCOLIGADA"):
        _validate_context({"CODCOLIGADA": "4"}, "3")
    with pytest.raises(RMJobError, match="não permitidos"):
        _validate_context({"CODCOLIGADA": "3", "Authorization": "Basic xyz"}, "3")


@pytest.mark.asyncio
async def test_read_page_accepts_only_json_list_and_enforces_limit():
    async def handler(_request):
        return httpx.Response(200, json=[{"CODCOLIGADA": "3", "RA": "00017"}])

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        rows = await _read_page(
            client, endpoint="https://rm.ies/rest/EduAlunoData",
            offset=0, limit=10, max_bytes=1024,
        )
    assert rows == [{"CODCOLIGADA": "3", "RA": "00017"}]


@pytest.mark.asyncio
async def test_read_page_classifies_rate_limit_as_transient():
    async def handler(_request):
        return httpx.Response(429, json={"error": "rate limit"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(RMTransientJobError):
            await _read_page(
                client, endpoint="https://rm.ies/rest/EduAlunoData",
                offset=0, limit=10, max_bytes=1024,
            )


@pytest.mark.asyncio
async def test_read_page_rejects_unexpected_response_shape():
    async def handler(_request):
        return httpx.Response(200, json={"items": [{"CODCOLIGADA": "3", "RA": "17"}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(RMJobError, match="lista JSON"):
            await _read_page(
                client, endpoint="https://rm.ies/rest/EduAlunoData",
                offset=0, limit=10, max_bytes=1024,
            )


def test_roster_identity_requires_text_ra_to_preserve_leading_zeroes():
    assert _normalize_roster_record({"CODCOLIGADA": "3", "RA": "00017", "NOME": "Sensitive"}, "3") == {
        "CODCOLIGADA": "3", "RA": "00017"
    }
    with pytest.raises(RMJobError, match="texto"):
        _normalize_roster_record({"CODCOLIGADA": "3", "RA": 17}, "3")


def test_executor_requires_explicit_installation_homologation(monkeypatch):
    monkeypatch.delenv("RM_SYNC_ENABLE_EXECUTOR", raising=False)
    monkeypatch.delenv("RM_SYNC_EDUALUNODATA_CONTRACT_CONFIRMED", raising=False)
    with pytest.raises(RMJobError, match="desabilitado"):
        _assert_executor_contract_enabled()
    monkeypatch.setenv("RM_SYNC_ENABLE_EXECUTOR", "true")
    with pytest.raises(RMJobError, match="não foi homologado"):
        _assert_executor_contract_enabled()
    monkeypatch.setenv("RM_SYNC_EDUALUNODATA_CONTRACT_CONFIRMED", "true")
    _assert_executor_contract_enabled()



def test_rm_connection_repr_does_not_expose_password():
    from app.services.connectors.totvs_rm_executor import RMConnection

    connection = RMConnection("https://rm.example", "integration-user", "secret-password", {})
    assert "secret-password" not in repr(connection)
