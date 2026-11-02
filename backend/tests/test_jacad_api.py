from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from app.services.connectors.erp import JacadConnector
from app.services.connectors.jacad_api import (
    JacadApiClient,
    JacadConnectionError,
    decrypt_api_token,
    encrypt_api_token,
    validate_jacad_base_url,
)


def test_jacad_base_url_requires_official_https_origin():
    assert validate_jacad_base_url("https://ies-demo.jacad.com.br/") == "https://ies-demo.jacad.com.br"
    with pytest.raises(ValueError):
        validate_jacad_base_url("http://ies-demo.jacad.com.br")
    with pytest.raises(ValueError):
        validate_jacad_base_url("https://example.com")
    with pytest.raises(ValueError):
        validate_jacad_base_url("https://127.0.0.1")


def test_jacad_credential_encryption_roundtrip(monkeypatch):
    import app.services.connectors.jacad_api as module

    monkeypatch.setattr(module, "get_settings", lambda: SimpleNamespace(secret_key="test-secret-key-for-jacad-encryption"))
    encrypted = encrypt_api_token("token-123")
    assert encrypted != "token-123"
    assert decrypt_api_token(encrypted) == "token-123"


def test_jacad_native_student_payload_maps_ra_and_identity_fields():
    records = JacadConnector().transform({
        "elements": [
            {
                "idAluno": 901,
                "ra": "RA-2026-001",
                "nome": "Ana Silva",
                "email": "ana@example.edu.br",
                "dataAlteracao": "2026-10-31T10:00:00Z",
            },
            {"idAluno": 902, "nome": "Aluno sem RA"},
            {"idAluno": 903, "ra": "RA-003", "nome": ""},
        ]
    })
    assert len(records) == 2
    assert records[0]["matricula"] == "RA-2026-001"
    assert records[0]["nome"] == "Ana Silva"
    assert records[0]["email"] == "ana@example.edu.br"
    assert records[0]["dias_sem_login"] is None
    assert records[0]["presenca_percentual"] is None
    assert records[0]["nota_media"] is None
    assert records[0]["reprovacoes"] is None
    assert records[1]["matricula"] == "902"


@pytest.mark.asyncio
async def test_jacad_api_client_authenticates_and_follows_cursor_pages():
    seen = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/api/v1/auth/token":
            assert request.headers["token"] == "access-token"
            return httpx.Response(200, json={"token": "jwt-session", "expiresIn": 3600})
        assert request.headers["authorization"] == "Bearer jwt-session"
        assert request.url.path == "/api/v2/academico/alunos"
        if request.url.params.get("idCursor") == "200":
            return httpx.Response(200, json={"page": {"idCursorProximo": 0}, "elements": [{"idAluno": 2}]})
        return httpx.Response(200, json={"page": {"idCursor": 0, "idCursorProximo": 200}, "elements": [{"idAluno": 1}]})

    client = JacadApiClient(
        "https://ies-demo.jacad.com.br",
        "access-token",
        transport=httpx.MockTransport(handler),
    )
    try:
        rows = await client.fetch_students(page_size=100)
    finally:
        await client.close()

    assert [row["idAluno"] for row in rows] == [1, 2]
    student_requests = [request for request in seen if request.url.path.endswith("/alunos")]
    assert len(student_requests) == 2
    assert student_requests[0].url.params["pageSize"] == "100"
    assert student_requests[0].url.params["idCursor"] == "0"
    assert student_requests[1].url.params["idCursor"] == "200"


@pytest.mark.asyncio
async def test_jacad_api_client_stops_on_repeated_cursor():
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/auth/token":
            return httpx.Response(200, json={"token": "jwt-session"})
        return httpx.Response(200, json={"page": {"idCursorProximo": 7}, "elements": [{"idAluno": 1}]})

    client = JacadApiClient("https://ies-demo.jacad.com.br", "access-token", transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(JacadConnectionError, match="Cursor JACAD repetido"):
            await client.fetch_students(page_size=1)
    finally:
        await client.close()
