from __future__ import annotations

import re

from app.agents.base import SendResult
from app.core.config import get_settings


async def test_email_otp_login_is_single_use(client, tenant_factory, monkeypatch):
    await tenant_factory(slug="default", name="IES Demo")
    settings = get_settings()
    provisioned = await client.post(
        "/api/v1/auth/admin/users",
        headers={"X-Admin-Secret": settings.secret_key},
        json={
            "tenant_slug": "default",
            "display_name": "João Teste",
            "email": "joao-otp@mira.test",
            "password": "UmaSenhaForte#2026",
            "phone": "+5511987654321",
        },
    )
    assert provisioned.status_code == 201, provisioned.text

    monkeypatch.setattr(settings, "resend_api_key", "test-key")
    monkeypatch.setattr(settings, "email_from", "Mira <no-reply@example.test>")
    sent: list[tuple[str, str, str]] = []

    async def fake_send(*, to: str, subject: str, body: str, idempotency_key=None):
        sent.append((to, subject, body))
        return SendResult(ok=True, channel="email", provider="resend")

    import app.api.auth as auth_api

    monkeypatch.setattr(auth_api, "send_email_resend", fake_send)
    requested = await client.post(
        "/api/v1/auth/email/request", json={"email": "JOAO-OTP@mira.test"}
    )
    assert requested.status_code == 202
    assert "Se o e-mail estiver cadastrado" in requested.json()["message"]
    assert sent[0][0] == "joao-otp@mira.test"
    code_match = re.search(r"\b(\d{6})\b", sent[0][2])
    assert code_match

    verified = await client.post(
        "/api/v1/auth/email/verify",
        json={"email": "joao-otp@mira.test", "code": code_match.group(1)},
    )
    assert verified.status_code == 200, verified.text
    assert verified.json().get("access_token")

    replay = await client.post(
        "/api/v1/auth/email/verify",
        json={"email": "joao-otp@mira.test", "code": code_match.group(1)},
    )
    assert replay.status_code == 401
