"""Testes de integração da Wave 2: políticas institucionais e sessões MFA."""
from datetime import datetime, timezone

from app.core.mfa import encrypt_totp_secret, totp_at
from app.core.mira_security import hash_password
from app.models.auth import MfaTenantPolicy, User


async def test_required_role_forces_enrollment_before_session(client, db_session, tenant_factory):
    tenant, _key = await tenant_factory(slug="mfa-required-role")
    policy = MfaTenantPolicy(
        tenant_id=tenant.id,
        require_mfa_all=False,
        required_roles=["operator"],
    )
    user = User(
        tenant_id=tenant.id,
        display_name="Operador",
        email="operator-mfa@example.test",
        password_hash=hash_password("StrongPassword#2026"),
        role="operator",
        is_active=True,
    )
    db_session.add_all([policy, user])
    await db_session.commit()

    login = await client.post(
        "/api/v1/auth/login/password",
        json={"email": user.email, "password": "StrongPassword#2026"},
    )
    assert login.status_code == 200
    challenge = login.json()
    assert challenge["mfa_enrollment_required"] is True
    assert challenge["mfa_required"] is False
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
    token = confirmed.json()["access_token"]

    protected = await client.get(
        "/api/v1/org/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert protected.status_code == 200

    next_login = await client.post(
        "/api/v1/auth/login/password",
        json={"email": user.email, "password": "StrongPassword#2026"},
    )
    assert next_login.status_code == 200
    assert next_login.json()["mfa_required"] is True
    assert "access_token" not in next_login.json()


async def test_user_can_revoke_another_session_without_revoking_current(client, db_session, tenant_factory):
    tenant, _key = await tenant_factory(slug="mfa-session-owner")
    user = User(
        tenant_id=tenant.id,
        display_name="Session Owner",
        email="session-owner@example.test",
        password_hash=hash_password("StrongPassword#2026"),
        role="viewer",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()

    payload = {"email": user.email, "password": "StrongPassword#2026"}
    first = await client.post("/api/v1/auth/login/password", json=payload)
    second = await client.post("/api/v1/auth/login/password", json=payload)
    assert first.status_code == second.status_code == 200
    first_token = first.json()["access_token"]
    second_token = second.json()["access_token"]

    headers = {"Authorization": f"Bearer {first_token}"}
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
        headers={"Authorization": f"Bearer {second_token}"},
    )
    assert still_valid.status_code == 200
    assert revoked_token.status_code == 401


async def test_session_listing_is_scoped_to_current_user_and_tenant(client, db_session, tenant_factory):
    tenant_a, _key_a = await tenant_factory(slug="mfa-session-tenant-a")
    tenant_b, _key_b = await tenant_factory(slug="mfa-session-tenant-b")
    user_a = User(
        tenant_id=tenant_a.id,
        display_name="Usuário A",
        email="session-a@example.test",
        password_hash=hash_password("StrongPassword#2026"),
        role="viewer",
        is_active=True,
    )
    user_b = User(
        tenant_id=tenant_b.id,
        display_name="Usuário B",
        email="session-b@example.test",
        password_hash=hash_password("StrongPassword#2026"),
        role="viewer",
        is_active=True,
    )
    db_session.add_all([user_a, user_b])
    await db_session.commit()

    login_a = await client.post(
        "/api/v1/auth/login/password",
        json={"email": user_a.email, "password": "StrongPassword#2026"},
    )
    login_b = await client.post(
        "/api/v1/auth/login/password",
        json={"email": user_b.email, "password": "StrongPassword#2026"},
    )
    assert login_a.status_code == login_b.status_code == 200

    sessions_a = await client.get(
        "/api/v1/auth/mfa/sessions",
        headers={"Authorization": f"Bearer {login_a.json()['access_token']}"},
    )
    sessions_b = await client.get(
        "/api/v1/auth/mfa/sessions",
        headers={"Authorization": f"Bearer {login_b.json()['access_token']}"},
    )
    assert sessions_a.status_code == sessions_b.status_code == 200
    assert len(sessions_a.json()["sessions"]) == 1
    assert len(sessions_b.json()["sessions"]) == 1
    assert sessions_a.json()["sessions"][0]["id"] != sessions_b.json()["sessions"][0]["id"]



async def test_policy_change_revokes_old_sessions_and_keeps_admin_session(client, db_session, tenant_factory):
    tenant, _key = await tenant_factory(slug="mfa-policy-change")
    from app.core.mfa import new_totp_secret\n    secret = new_totp_secret()
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

    login = await client.post(
        "/api/v1/auth/login/password",
        json={"email": admin.email, "password": "StrongPassword#2026"},
    )
    assert login.status_code == 200
    challenge = login.json()
    assert challenge["mfa_required"] is True

    code, _step = totp_at(secret)
    verified = await client.post(
        "/api/v1/auth/mfa/login/verify",
        json={"challenge_token": challenge["challenge_token"], "code": code},
    )
    assert verified.status_code == 200
    old_token = verified.json()["access_token"]

    old_session = await client.get(
        "/api/v1/org/me",
        headers={"Authorization": f"Bearer {old_token}"},
    )
    assert old_session.status_code == 200

    changed = await client.put(
        "/api/v1/auth/mfa/policy",
        headers={"Authorization": f"Bearer {old_token}"},
        json={"require_mfa_all": True, "required_roles": []},
    )
    assert changed.status_code == 200
    assert changed.json()["require_mfa_all"] is True
    assert changed.json()["access_token"]

    rejected_old_token = await client.get(
        "/api/v1/org/me",
        headers={"Authorization": f"Bearer {old_token}"},
    )
    accepted_new_token = await client.get(
        "/api/v1/org/me",
        headers={"Authorization": f"Bearer {changed.json()['access_token']}"},
    )
    assert rejected_old_token.status_code == 401
    assert accepted_new_token.status_code == 200
