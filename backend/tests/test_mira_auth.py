"""Fluxos de autenticação humana com TOTP obrigatório."""
from __future__ import annotations

import re
from time import time
from datetime import datetime, timezone

from app.agents.base import SendResult
from app.core.config import get_settings
from app.core.mfa import encrypt_totp_secret, new_totp_secret, totp_at
from app.core.mira_security import hash_password
from app.models.auth import User


async def _create_user(db_session, tenant, *, email="user@example.test", phone=None):
    secret = new_totp_secret()
    user = User(
        tenant_id=tenant.id,
        display_name="Test User",
        email=email,
        phone_e164=phone,
        password_hash=hash_password("Test_Password_2026!"),
        role="operator",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    return user, secret


async def _complete_enrollment(client, challenge):
    assert challenge["mfa_enrollment_required"] is True
    enrollment = await client.post(
        "/api/v1/auth/mfa/login/enroll",
        json={"challenge_token": challenge["challenge_token"]},
    )
    assert enrollment.status_code == 200, enrollment.text
    secret = enrollment.json()["secret"]
    code, _step = totp_at(secret)
    confirmed = await client.post(
        "/api/v1/auth/mfa/login/enroll/confirm",
        json={"challenge_token": challenge["challenge_token"], "code": code},
    )
    assert confirmed.status_code == 200, confirmed.text
    return confirmed.json(), secret


async def _complete_totp_login(client, challenge, secret):
    assert challenge["mfa_required"] is True
    next_step_timestamp = (int(time()) // 30 + 1) * 30
    code, _step = totp_at(secret, timestamp=next_step_timestamp)
    verified = await client.post(
        "/api/v1/auth/mfa/login/verify",
        json={"challenge_token": challenge["challenge_token"], "code": code},
    )
    assert verified.status_code == 200, verified.text
    return verified.json()


async def test_password_login_requires_enrollment_before_issuing_a_session(
    client, db_session, tenant_factory
):
    tenant, _key = await tenant_factory(slug="password-totp")
    user, _secret = await _create_user(db_session, tenant)
    response = await client.post(
        "/api/v1/auth/login/password",
        json={"email": user.email, "password": "Test_Password_2026!"},
    )
    assert response.status_code == 200
    assert response.json()["mfa_enrollment_required"] is True
    assert "access_token" not in response.json()

    payload, _secret = await _complete_enrollment(client, response.json())
    protected = await client.get(
        "/api/v1/org/me",
        headers={"Authorization": f"Bearer {payload['access_token']}"},
    )
    assert protected.status_code == 200


async def test_password_login_rejects_wrong_password(client, db_session, tenant_factory):
    tenant, _key = await tenant_factory(slug="password-invalid")
    user, _secret = await _create_user(db_session, tenant)
    response = await client.post(
        "/api/v1/auth/login/password",
        json={"email": user.email, "password": "incorrect"},
    )
    assert response.status_code == 401


async def test_admin_user_provisioning_rejects_wrong_secret(client, tenant_factory):
    await tenant_factory(slug="default", name="Demo")
    response = await client.post(
        "/api/v1/auth/admin/users",
        headers={"X-Admin-Secret": "wrong-secret"},
        json={
            "tenant_slug": "default",
            "display_name": "Test User",
            "email": "provision@example.test",
            "password": "Test_Password_2026!",
        },
    )
    assert response.status_code == 403


async def test_invalid_password_validation_does_not_echo_password(client, tenant_factory):
    await tenant_factory(slug="default", name="Demo")
    attempted_password = "badpass"
    response = await client.post(
        "/api/v1/auth/admin/users",
        headers={"X-Admin-Secret": get_settings().secret_key},
        json={
            "tenant_slug": "default",
            "display_name": "Test User",
            "email": "invalid@example.test",
            "password": attempted_password,
        },
    )
    assert response.status_code == 422
    assert attempted_password not in response.text
    assert "input" not in response.json()["detail"][0]


async def test_whatsapp_otp_is_followed_by_required_totp(
    client, db_session, tenant_factory, monkeypatch
):
    tenant, _key = await tenant_factory(slug="whatsapp-totp")
    phone = "+5521990000001"
    user, _secret = await _create_user(db_session, tenant, phone=phone)
    settings = get_settings()
    monkeypatch.setattr(settings, "waha_api_url", "https://waha.test")
    monkeypatch.setattr(settings, "waha_api_key", "test-key")
    sent: list[str] = []

    async def fake_send(*, to: str, message: str):
        assert to == phone
        sent.append(message)
        return SendResult(ok=True, channel="whatsapp", provider="waha")

    import app.api.auth as auth_api
    monkeypatch.setattr(auth_api, "send_whatsapp", fake_send)

    requested = await client.post(
        "/api/v1/auth/whatsapp/request",
        json={"phone": phone},
    )
    assert requested.status_code == 202
    code_match = re.search(r"\b(\d{6})\b", sent[0])
    assert code_match

    verified = await client.post(
        "/api/v1/auth/whatsapp/verify",
        json={"phone": phone, "code": code_match.group(1)},
    )
    assert verified.status_code == 200
    assert verified.json()["mfa_enrollment_required"] is True
    assert "access_token" not in verified.json()

    payload, _secret = await _complete_enrollment(client, verified.json())
    protected = await client.get(
        "/api/v1/org/me",
        headers={"Authorization": f"Bearer {payload['access_token']}"},
    )
    assert protected.status_code == 200

    replay = await client.post(
        "/api/v1/auth/whatsapp/verify",
        json={"phone": phone, "code": code_match.group(1)},
    )
    assert replay.status_code == 401


async def test_password_reset_revokes_sessions_and_preserves_required_totp(
    client, db_session, tenant_factory, monkeypatch
):
    tenant, _key = await tenant_factory(slug="password-reset-totp")
    user, _secret = await _create_user(db_session, tenant, email="reset@example.test")
    first_login = await client.post(
        "/api/v1/auth/login/password",
        json={"email": user.email, "password": "Test_Password_2026!"},
    )
    assert first_login.status_code == 200
    old_session, secret = await _complete_enrollment(client, first_login.json())

    settings = get_settings()
    monkeypatch.setattr(settings, "resend_api_key", "test-key")
    monkeypatch.setattr(settings, "email_from", "Demo <no-reply@example.test>")
    emails: list[str] = []

    async def fake_send(*, to: str, subject: str, body: str):
        assert to == user.email
        emails.append(body)
        return SendResult(ok=True, channel="email", provider="resend")

    import app.api.auth as auth_api
    monkeypatch.setattr(auth_api, "send_email_resend", fake_send)

    requested = await client.post(
        "/api/v1/auth/password/forgot",
        json={"email": user.email},
    )
    assert requested.status_code == 202
    token_match = re.search(r"reset-password\?token=([A-Za-z0-9_-]+)", emails[0])
    assert token_match

    reset = await client.post(
        "/api/v1/auth/password/reset",
        json={"token": token_match.group(1), "new_password": "New_Test_Password_2026!"},
    )
    assert reset.status_code == 200, reset.text

    revoked = await client.get(
        "/api/v1/org/me",
        headers={"Authorization": f"Bearer {old_session['access_token']}"},
    )
    assert revoked.status_code == 401

    replay = await client.post(
        "/api/v1/auth/password/reset",
        json={"token": token_match.group(1), "new_password": "Other_Test_Password_2026!"},
    )
    assert replay.status_code == 400

    old_login = await client.post(
        "/api/v1/auth/login/password",
        json={"email": user.email, "password": "Test_Password_2026!"},
    )
    assert old_login.status_code == 401
    new_login = await client.post(
        "/api/v1/auth/login/password",
        json={"email": user.email, "password": "New_Test_Password_2026!"},
    )
    assert new_login.status_code == 200
    assert new_login.json()["mfa_required"] is True
    reauthenticated = await _complete_totp_login(client, new_login.json(), secret)
    assert reauthenticated["access_token"]


async def test_email_otp_login_sends_code_and_requires_mfa(
    client, db_session, tenant_factory, monkeypatch
):
    tenant, _key = await tenant_factory(slug="email-otp-login")
    user, _secret = await _create_user(db_session, tenant, email="email-otp@example.test")
    settings = get_settings()
    monkeypatch.setattr(settings, "resend_api_key", "test-key")
    monkeypatch.setattr(settings, "email_from", "MIRA <no-reply@example.test>")
    sent: list[str] = []

    async def fake_send(*, to: str, subject: str, body: str):
        assert to == user.email
        assert subject == "Seu código de acesso à MIRA"
        sent.append(body)
        return SendResult(ok=True, channel="email", provider="resend")

    import app.api.auth as auth_api
    monkeypatch.setattr(auth_api, "send_email_resend", fake_send)

    requested = await client.post(
        "/api/v1/auth/email/request",
        json={"email": " EMAIL-OTP@example.test "},
    )
    assert requested.status_code == 202
    assert "Se houver uma conta ativa" in requested.json()["message"]
    code_match = re.search(r"\b(\d{6})\b", sent[0])
    assert code_match

    verified = await client.post(
        "/api/v1/auth/email/verify",
        json={"email": user.email, "code": code_match.group(1)},
    )
    assert verified.status_code == 200, verified.text
    assert verified.json()["mfa_enrollment_required"] is True
    assert "access_token" not in verified.json()

    replay = await client.post(
        "/api/v1/auth/email/verify",
        json={"email": user.email, "code": code_match.group(1)},
    )
    assert replay.status_code == 401


async def test_email_otp_request_routes_verified_unknown_email_to_onboarding(
    client, monkeypatch
):
    settings = get_settings()
    monkeypatch.setattr(settings, "resend_api_key", "test-key")
    monkeypatch.setattr(settings, "email_from", "MIRA <no-reply@example.test>")
    sent: list[str] = []

    async def fake_send(*, to: str, subject: str, body: str):
        assert to == "new-user@example.test"
        sent.append(body)
        return SendResult(ok=True, channel="email", provider="resend")

    import app.api.auth as auth_api
    monkeypatch.setattr(auth_api, "send_email_resend", fake_send)

    requested = await client.post(
        "/api/v1/auth/email/request",
        json={"email": "new-user@example.test"},
    )
    assert requested.status_code == 202
    assert len(sent) == 1
    code_match = re.search(r"\b(\d{6})\b", sent[0])
    assert code_match

    verified = await client.post(
        "/api/v1/auth/email/verify",
        json={"email": "new-user@example.test", "code": code_match.group(1)},
    )
    assert verified.status_code == 200, verified.text
    assert verified.json() == {
        "onboarding_required": True,
        "email": "new-user@example.test",
    }
    assert "access_token" not in verified.json()

    replay = await client.post(
        "/api/v1/auth/email/verify",
        json={"email": "new-user@example.test", "code": code_match.group(1)},
    )
    assert replay.status_code == 401


async def test_email_otp_rejects_invalid_codes_and_enforces_attempt_limit(
    client, db_session, tenant_factory, monkeypatch
):
    tenant, _key = await tenant_factory(slug="email-otp-attempts")
    user, _secret = await _create_user(db_session, tenant, email="otp-attempts@example.test")
    settings = get_settings()
    monkeypatch.setattr(settings, "resend_api_key", "test-key")
    monkeypatch.setattr(settings, "email_from", "MIRA <no-reply@example.test>")

    sent: list[str] = []

    async def fake_send(*, to: str, subject: str, body: str):
        sent.append(body)
        return SendResult(ok=True, channel="email", provider="resend")

    import app.api.auth as auth_api
    monkeypatch.setattr(auth_api, "send_email_resend", fake_send)
    await client.post("/api/v1/auth/email/request", json={"email": user.email})
    actual_code = re.search(r"\\b(\\d{6})\\b", sent[0])
    assert actual_code
    wrong_code = f"{(int(actual_code.group(1)) + 1) % 1_000_000:06d}"

    for _attempt in range(5):
        response = await client.post(
            "/api/v1/auth/email/verify",
            json={"email": user.email, "code": wrong_code},
        )
        assert response.status_code == 401

    blocked = await client.post(
        "/api/v1/auth/email/verify",
        json={"email": user.email, "code": wrong_code},
    )
    assert blocked.status_code == 401
