"""Testes HTTP de políticas globais MFA e sessões revogáveis."""
from datetime import datetime, timezone
from time import time

from sqlalchemy import select

from app.core.mfa import encrypt_totp_secret, new_totp_secret, totp_at
from app.core.mira_security import hash_password
from app.core.user_sessions import create_user_session
from app.models.auth import User, UserSession


async def _login_with_totp(client, *, email, password, secret, next_step=False):
    login = await client.post(
        "/api/v1/auth/login/password",
        json={"email": email, "password": password},
    )
    assert login.status_code == 200, login.text
    challenge = login.json()
    assert challenge["mfa_required"] is True
    assert "access_token" not in challenge

    timestamp = (int(time()) // 30 + (1 if next_step else 0)) * 30
    code, _step = totp_at(secret, timestamp=timestamp)
    verified = await client.post(
        "/api/v1/auth/mfa/login/verify",
        json={"challenge_token": challenge["challenge_token"], "code": code},
    )
    assert verified.status_code == 200, verified.text
    return verified.json()


async def test_every_role_without_tenant_policy_must_enroll_before_session(
    client, db_session, tenant_factory
):
    tenant, _key = await tenant_factory(slug="mfa-global-policy")
    user = User(
        tenant_id=tenant.id,
        display_name="Visualizador",
        email="global-viewer@example.test",
        password_hash=hash_password("StrongPassword#2026"),
        role="viewer",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()

    login = await client.post(
        "/api/v1/auth/login/password",
        json={"email": user.email, "password": "StrongPassword#2026"},
    )
    assert login.status_code == 200
    challenge = login.json()
    assert challenge["mfa_enrollment_required"] is True
    assert "access_token" not in challenge

    enrollment = await client.post(
        "/api/v1/auth/mfa/login/enroll",
        json={"challenge_token": challenge["challenge_token"]},
    )
    assert enrollment.status_code == 200
    secret = enrollment.json()["secret"]
    code, _step = totp_at(secret)

    confirmed = await client.post(
        "/api/v1/auth/mfa/login/enroll/confirm",
        json={"challenge_token": challenge["challenge_token"], "code": code},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["enabled"] is True
    assert len(confirmed.json()["recovery_codes"]) == 10

    protected = await client.get(
        "/api/v1/org/me",
        headers={"Authorization": f"Bearer {confirmed.json()['access_token']}"},
    )
    assert protected.status_code == 200

    next_login = await client.post(
        "/api/v1/auth/login/password",
        json={"email": user.email, "password": "StrongPassword#2026"},
    )
    assert next_login.status_code == 200
    assert next_login.json()["mfa_required"] is True
    assert "access_token" not in next_login.json()


async def test_legacy_aal1_session_is_revoked_by_global_mfa_requirement(
    client, db_session, tenant_factory
):
    tenant, _key = await tenant_factory(slug="mfa-legacy-session")
    user = User(
        tenant_id=tenant.id,
        display_name="Legacy User",
        email="legacy-session@example.test",
        password_hash=hash_password("StrongPassword#2026"),
        role="operator",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    legacy_token, _ttl = create_user_session(db_session, user, tenant, aal=1)
    await db_session.commit()

    rejected = await client.get(
        "/api/v1/org/me",
        headers={"Authorization": f"Bearer {legacy_token}"},
    )
    assert rejected.status_code == 401
    assert "TOTP obrigatório" in rejected.json()["detail"]

    sessions = (
        await db_session.execute(select(UserSession).where(UserSession.user_id == user.id))
    ).scalars().all()
    assert len(sessions) == 1
    assert sessions[0].revoked_at is not None
    assert sessions[0].revoke_reason == "global_mfa_required"


async def test_user_can_revoke_another_totp_session_without_revoking_current(
    client, db_session, tenant_factory
):
    tenant, _key = await tenant_factory(slug="mfa-session-owner")
    secret = new_totp_secret()
    user = User(
        tenant_id=tenant.id,
        display_name="Session Owner",
        email="session-owner@example.test",
        password_hash=hash_password("StrongPassword#2026"),
        role="viewer",
        is_active=True,
        mfa_totp_secret_encrypted=encrypt_totp_secret(secret),
        mfa_enabled_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    await db_session.commit()

    first = await _login_with_totp(
        client, email=user.email, password="StrongPassword#2026", secret=secret
    )
    second = await _login_with_totp(
        client, email=user.email, password="StrongPassword#2026",
        secret=secret, next_step=True,
    )
    headers = {"Authorization": f"Bearer {first['access_token']}"}
    listing = await client.get("/api/v1/auth/mfa/sessions", headers=headers)
    assert listing.status_code == 200
    sessions = listing.json()["sessions"]
    assert len(sessions) == 2
    other = next(item for item in sessions if not item["current"])

    revoked = await client.delete(
        f"/api/v1/auth/mfa/sessions/{other['id']}",
        headers=headers,
    )
    assert revoked.status_code == 200

    still_valid = await client.get("/api/v1/org/me", headers=headers)
    revoked_token = await client.get(
        "/api/v1/org/me",
        headers={"Authorization": f"Bearer {second['access_token']}"},
    )
    assert still_valid.status_code == 200
    assert revoked_token.status_code == 401


async def test_session_listing_is_scoped_to_current_user_and_tenant(
    client, db_session, tenant_factory
):
    tenant_a, _key_a = await tenant_factory(slug="mfa-session-tenant-a")
    tenant_b, _key_b = await tenant_factory(slug="mfa-session-tenant-b")
    secret_a, secret_b = new_totp_secret(), new_totp_secret()
    user_a = User(
        tenant_id=tenant_a.id,
        display_name="Usuário A",
        email="session-a@example.test",
        password_hash=hash_password("StrongPassword#2026"),
        role="viewer",
        is_active=True,
        mfa_totp_secret_encrypted=encrypt_totp_secret(secret_a),
        mfa_enabled_at=datetime.now(timezone.utc),
    )
    user_b = User(
        tenant_id=tenant_b.id,
        display_name="Usuário B",
        email="session-b@example.test",
        password_hash=hash_password("StrongPassword#2026"),
        role="viewer",
        is_active=True,
        mfa_totp_secret_encrypted=encrypt_totp_secret(secret_b),
        mfa_enabled_at=datetime.now(timezone.utc),
    )
    db_session.add_all([user_a, user_b])
    await db_session.commit()

    login_a = await _login_with_totp(
        client, email=user_a.email, password="StrongPassword#2026", secret=secret_a
    )
    login_b = await _login_with_totp(
        client, email=user_b.email, password="StrongPassword#2026", secret=secret_b
    )

    sessions_a = await client.get(
        "/api/v1/auth/mfa/sessions",
        headers={"Authorization": f"Bearer {login_a['access_token']}"},
    )
    sessions_b = await client.get(
        "/api/v1/auth/mfa/sessions",
        headers={"Authorization": f"Bearer {login_b['access_token']}"},
    )
    assert sessions_a.status_code == sessions_b.status_code == 200
    assert len(sessions_a.json()["sessions"]) == 1
    assert len(sessions_b.json()["sessions"]) == 1
    assert sessions_a.json()["sessions"][0]["id"] != sessions_b.json()["sessions"][0]["id"]


async def test_global_mfa_policy_cannot_be_disabled_or_limited(
    client, db_session, tenant_factory
):
    tenant, _key = await tenant_factory(slug="mfa-policy-immutable")
    secret = new_totp_secret()
    admin = User(
        tenant_id=tenant.id,
        display_name="Admin MFA",
        email="policy-admin@example.test",
        password_hash=hash_password("StrongPassword#2026"),
        role="admin",
        is_active=True,
        mfa_totp_secret_encrypted=encrypt_totp_secret(secret),
        mfa_enabled_at=datetime.now(timezone.utc),
    )
    db_session.add(admin)
    await db_session.commit()

    login = await _login_with_totp(
        client, email=admin.email, password="StrongPassword#2026", secret=secret
    )
    headers = {"Authorization": f"Bearer {login['access_token']}"}

    policy = await client.get("/api/v1/auth/mfa/policy", headers=headers)
    assert policy.status_code == 200
    assert policy.json()["require_mfa_all"] is True
    assert policy.json()["required_roles"] == []
    assert policy.json()["enforcement_scope"] == "global"
    assert policy.json()["mutable"] is False

    disabled = await client.put(
        "/api/v1/auth/mfa/policy",
        headers=headers,
        json={"require_mfa_all": False, "required_roles": []},
    )
    assert disabled.status_code == 409

    limited = await client.put(
        "/api/v1/auth/mfa/policy",
        headers=headers,
        json={"require_mfa_all": False, "required_roles": ["admin"]},
    )
    assert limited.status_code == 409

    disable_totp = await client.post("/api/v1/auth/mfa/disable", headers=headers)
    assert disable_totp.status_code == 409
