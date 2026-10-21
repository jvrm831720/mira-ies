"""Fluxos de autenticação Mira com providers externos simulados."""
from __future__ import annotations

import re

from app.agents.base import SendResult
from app.core.config import get_settings


async def _provision(client, *, phone: str = "11987654321"):
    settings = get_settings()
    response = await client.post(
        "/api/v1/auth/admin/users",
        headers={"X-Admin-Secret": settings.secret_key},
        json={
            "tenant_slug": "default",
            "display_name": "João Mendes",
            "email": "joao@mira.test",
            "password": "UmaSenhaForte#2026",
            "phone": phone,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _ensure_default_tenant(tenant_factory):
    tenant, _key = await tenant_factory(slug="default", name="IES Demo")
    return tenant


async def test_password_login_issues_session_token_for_tenant(client, tenant_factory):
    await _ensure_default_tenant(tenant_factory)
    await _provision(client)

    response = await client.post(
        "/api/v1/auth/login/password",
        json={"email": "JOAO@MIRA.TEST", "password": "UmaSenhaForte#2026"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["token_type"] == "bearer"
    assert payload["user"]["email"] == "joao@mira.test"

    protected = await client.get(
        "/api/v1/agents/status",
        headers={"Authorization": f"Bearer {payload['access_token']}"},
    )
    assert protected.status_code == 200


async def test_password_login_rejects_wrong_password(client, tenant_factory):
    await _ensure_default_tenant(tenant_factory)
    await _provision(client)

    response = await client.post(
        "/api/v1/auth/login/password",
        json={"email": "joao@mira.test", "password": "senha-incorreta"},
    )
    assert response.status_code == 401
    assert "inválido" in response.json()["detail"]


async def test_admin_user_provisioning_rejects_wrong_secret(client, tenant_factory):
    await _ensure_default_tenant(tenant_factory)
    response = await client.post(
        "/api/v1/auth/admin/users",
        headers={"X-Admin-Secret": "wrong-secret"},
        json={
            "tenant_slug": "default",
            "display_name": "User",
            "email": "user@mira.test",
            "password": "UmaSenhaForte#2026",
        },
    )
    assert response.status_code == 403


async def test_invalid_password_validation_does_not_echo_password(client):
    attempted_password = "too-short-secret"
    response = await client.post(
        "/api/v1/auth/admin/users",
        json={
            "tenant_slug": "default",
            "display_name": "User",
            "email": "user@mira.test",
            "password": attempted_password,
        },
    )
    assert response.status_code == 422
    assert attempted_password not in response.text
    assert "input" not in response.json()["detail"][0]


async def test_whatsapp_otp_login(client, tenant_factory, monkeypatch):
    await _ensure_default_tenant(tenant_factory)
    await _provision(client)
    settings = get_settings()
    monkeypatch.setattr(settings, "evolution_api_url", "https://evolution.test")
    monkeypatch.setattr(settings, "evolution_api_key", "test-key")
    sent: list[str] = []

    async def fake_send(*, to: str, message: str):
        assert to == "+5511987654321"
        sent.append(message)
        return SendResult(ok=True, channel="whatsapp", provider="evolution")

    import app.api.auth as auth_api
    monkeypatch.setattr(auth_api, "send_whatsapp_evolution", fake_send)

    requested = await client.post("/api/v1/auth/whatsapp/request", json={"phone": "11987654321"})
    assert requested.status_code == 202
    assert "Se o número estiver cadastrado" in requested.json()["message"]
    code_match = re.search(r"\b(\d{6})\b", sent[0])
    assert code_match

    verified = await client.post(
        "/api/v1/auth/whatsapp/verify",
        json={"phone": "+5511987654321", "code": code_match.group(1)},
    )
    assert verified.status_code == 200, verified.text
    token = verified.json()["access_token"]
    protected = await client.get(
        "/api/v1/agents/status", headers={"Authorization": f"Bearer {token}"}
    )
    assert protected.status_code == 200

    replay = await client.post(
        "/api/v1/auth/whatsapp/verify",
        json={"phone": "11987654321", "code": code_match.group(1)},
    )
    assert replay.status_code == 401


async def test_email_password_reset_is_single_use(client, tenant_factory, monkeypatch):
    await _ensure_default_tenant(tenant_factory)
    await _provision(client)
    old_session = await client.post(
        "/api/v1/auth/login/password",
        json={"email": "joao@mira.test", "password": "UmaSenhaForte#2026"},
    )
    assert old_session.status_code == 200
    settings = get_settings()
    monkeypatch.setattr(settings, "resend_api_key", "test-key")
    monkeypatch.setattr(settings, "email_from", "Mira <no-reply@example.test>")
    emails: list[str] = []

    async def fake_send(*, to: str, subject: str, body: str):
        assert to == "joao@mira.test"
        assert subject == "Redefinição de senha da Mira"
        emails.append(body)
        return SendResult(ok=True, channel="email", provider="resend")

    import app.api.auth as auth_api
    monkeypatch.setattr(auth_api, "send_email_resend", fake_send)

    requested = await client.post(
        "/api/v1/auth/password/forgot", json={"email": "JOAO@MIRA.TEST"}
    )
    assert requested.status_code == 202
    token_match = re.search(r"reset-password\?token=([A-Za-z0-9_-]+)", emails[0])
    assert token_match

    reset = await client.post(
        "/api/v1/auth/password/reset",
        json={"token": token_match.group(1), "new_password": "OutraSenhaForte#2026"},
    )
    assert reset.status_code == 200, reset.text
    revoked_session = await client.get(
        "/api/v1/agents/status",
        headers={"Authorization": f"Bearer {old_session.json()['access_token']}"},
    )
    assert revoked_session.status_code == 401
    replay = await client.post(
        "/api/v1/auth/password/reset",
        json={"token": token_match.group(1), "new_password": "MaisUmaSenha#2026"},
    )
    assert replay.status_code == 400

    old_login = await client.post(
        "/api/v1/auth/login/password",
        json={"email": "joao@mira.test", "password": "UmaSenhaForte#2026"},
    )
    assert old_login.status_code == 401
    new_login = await client.post(
        "/api/v1/auth/login/password",
        json={"email": "joao@mira.test", "password": "OutraSenhaForte#2026"},
    )
    assert new_login.status_code == 200
