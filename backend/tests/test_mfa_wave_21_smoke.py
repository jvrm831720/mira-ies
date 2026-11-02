"""Wave 2.1 HTTP smoke tests for MFA enrollment, login and session lifecycle."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.api.auth import _fingerprint, _token_digest
from app.api.org import _invite_token_hash
from app.core.mfa import (
    encrypt_totp_secret,
    new_totp_secret,
    recovery_code_hash,
    totp_at,
)
from app.core.mira_security import hash_password
from app.models.auth import (
    AuthChallenge,
    MfaRecoveryCode,
    MfaTenantPolicy,
    OrganizationInvite,
    User,
    UserSession,
)


def _totp_code(secret: str) -> str:
    code, _step = totp_at(secret)
    return code


async def test_smoke_optional_mfa_keeps_password_login_available(
    client, db_session, tenant_factory
):
    tenant, _key = await tenant_factory(slug="mfa-smoke-optional")
    user = User(
        tenant_id=tenant.id,
        display_name="Optional MFA",
        email="optional-mfa-smoke@example.test",
        password_hash=hash_password("StrongPassword#2026"),
        role="operator",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()

    login = await client.post(
        "/api/v1/auth/login/password",
        json={"email": user.email, "password": "StrongPassword#2026"},
    )

    assert login.status_code == 200
    assert login.json().get("access_token")
    assert "challenge_token" not in login.json()

    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    profile = await client.get("/api/v1/org/me", headers=headers)
    status = await client.get("/api/v1/auth/mfa/status", headers=headers)

    assert profile.status_code == 200
    assert status.status_code == 200
    assert status.json()["enabled"] is False


async def test_smoke_required_enrollment_totp_login_and_recovery_code_once(
    client, db_session, tenant_factory
):
    tenant, _key = await tenant_factory(slug="mfa-smoke-required")
    policy = MfaTenantPolicy(
        tenant_id=tenant.id,
        require_mfa_all=True,
        required_roles=[],
    )
    user = User(
        tenant_id=tenant.id,
        display_name="Required MFA",
        email="required-mfa-smoke@example.test",
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
    assert "access_token" not in challenge

    blocked = await client.get("/api/v1/org/me")
    assert blocked.status_code == 401

    enrollment = await client.post(
        "/api/v1/auth/mfa/login/enroll",
        json={"challenge_token": challenge["challenge_token"]},
    )
    assert enrollment.status_code == 200
    enrollment_data = enrollment.json()
    assert enrollment_data["secret"]
    assert enrollment_data["qr_code"].startswith("data:image/svg+xml;base64,")
    secret = enrollment_data["secret"]

    recovery_response = await client.post(
        "/api/v1/auth/mfa/login/enroll/confirm",
        json={
            "challenge_token": challenge["challenge_token"],
            "code": _totp_code(secret),
        },
    )
    assert recovery_response.status_code == 200
    confirmation = recovery_response.json()
    assert confirmation["enabled"] is True
    assert len(confirmation["recovery_codes"]) == 10
    assert len(set(confirmation["recovery_codes"])) == 10
    assert confirmation["access_token"]

    saved_codes = (
        await db_session.execute(
            select(MfaRecoveryCode).where(MfaRecoveryCode.user_id == user.id)
        )
    ).scalars().all()
    assert len(saved_codes) == 10
    assert all(row.tenant_id == tenant.id for row in saved_codes)
    stored_hashes = {row.code_hash for row in saved_codes}
    assert all(recovery_code_hash(code) in stored_hashes for code in confirmation["recovery_codes"])
    assert stored_hashes.isdisjoint(set(confirmation["recovery_codes"]))

    first_profile = await client.get(
        "/api/v1/org/me",
        headers={"Authorization": f"Bearer {confirmation['access_token']}"},
    )
    assert first_profile.status_code == 200

    next_login = await client.post(
        "/api/v1/auth/login/password",
        json={"email": user.email, "password": "StrongPassword#2026"},
    )
    assert next_login.status_code == 200
    assert next_login.json()["mfa_required"] is True
    assert "access_token" not in next_login.json()

    recovery_code = confirmation["recovery_codes"][0]
    recovered = await client.post(
        "/api/v1/auth/mfa/login/verify",
        json={
            "challenge_token": next_login.json()["challenge_token"],
            "code": recovery_code,
        },
    )
    assert recovered.status_code == 200
    assert recovered.json()["access_token"]

    reuse_login = await client.post(
        "/api/v1/auth/login/password",
        json={"email": user.email, "password": "StrongPassword#2026"},
    )
    assert reuse_login.status_code == 200
    reused = await client.post(
        "/api/v1/auth/mfa/login/verify",
        json={
            "challenge_token": reuse_login.json()["challenge_token"],
            "code": recovery_code,
        },
    )
    assert reused.status_code == 401
    assert "access_token" not in reused.json()


async def test_smoke_whatsapp_verification_obeys_required_mfa_policy(
    client, db_session, tenant_factory
):
    tenant, _key = await tenant_factory(slug="mfa-smoke-whatsapp")
    phone = "+5521999998888"
    user = User(
        tenant_id=tenant.id,
        display_name="WhatsApp MFA",
        email="whatsapp-mfa-smoke@example.test",
        phone_e164=phone,
        password_hash=hash_password("StrongPassword#2026"),
        role="operator",
        is_active=True,
    )
    policy = MfaTenantPolicy(
        tenant_id=tenant.id,
        require_mfa_all=False,
        required_roles=["operator"],
    )
    code = "381204"
    challenge = AuthChallenge(
        user_id=user.id,
        challenge_type="whatsapp_login",
        identifier_hash=_fingerprint("whatsapp", phone),
        token_hash=_token_digest("whatsapp", phone, code),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    db_session.add_all([user, policy, challenge])
    await db_session.commit()

    verified_whatsapp = await client.post(
        "/api/v1/auth/whatsapp/verify",
        json={"phone": phone, "code": code},
    )

    assert verified_whatsapp.status_code == 200
    assert verified_whatsapp.json()["mfa_enrollment_required"] is True
    assert "access_token" not in verified_whatsapp.json()


async def test_smoke_invite_acceptance_for_protected_role_requires_enrollment(
    client, db_session, tenant_factory
):
    tenant, _key = await tenant_factory(slug="mfa-smoke-invite")
    token = "invite-smoke-token-2026-unique"
    policy = MfaTenantPolicy(
        tenant_id=tenant.id,
        require_mfa_all=False,
        required_roles=["operator"],
    )
    invite = OrganizationInvite(
        tenant_id=tenant.id,
        email="invited-mfa-smoke@example.test",
        role="operator",
        token_hash=_invite_token_hash(token),
        status="pending",
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    db_session.add_all([policy, invite])
    await db_session.commit()

    accepted = await client.post(
        "/api/v1/org/invites/accept",
        json={
            "token": token,
            "password": "StrongPassword#2026",
            "phone": "21988887777",
            "display_name": "Invited Operator",
        },
    )

    assert accepted.status_code == 200
    assert accepted.json()["mfa_enrollment_required"] is True
    assert "access_token" not in accepted.json()

    enrollment = await client.post(
        "/api/v1/auth/mfa/login/enroll",
        json={"challenge_token": accepted.json()["challenge_token"]},
    )
    assert enrollment.status_code == 200


async def test_smoke_admin_can_revoke_member_sessions_after_totp_step_up(
    client, db_session, tenant_factory
):
    tenant, _key = await tenant_factory(slug="mfa-smoke-admin-revoke")
    secret = new_totp_secret()
    admin = User(
        tenant_id=tenant.id,
        display_name="MFA Admin",
        email="mfa-admin-revoke-smoke@example.test",
        password_hash=hash_password("StrongPassword#2026"),
        role="admin",
        is_active=True,
        mfa_totp_secret_encrypted=encrypt_totp_secret(secret),
        mfa_enabled_at=datetime.now(timezone.utc),
    )
    member = User(
        tenant_id=tenant.id,
        display_name="Member",
        email="mfa-member-revoke-smoke@example.test",
        password_hash=hash_password("StrongPassword#2026"),
        role="operator",
        is_active=True,
    )
    db_session.add_all([admin, member])
    await db_session.commit()

    admin_login = await client.post(
        "/api/v1/auth/login/password",
        json={"email": admin.email, "password": "StrongPassword#2026"},
    )
    assert admin_login.status_code == 200
    assert admin_login.json()["mfa_required"] is True

    admin_verified = await client.post(
        "/api/v1/auth/mfa/login/verify",
        json={
            "challenge_token": admin_login.json()["challenge_token"],
            "code": _totp_code(secret),
        },
    )
    assert admin_verified.status_code == 200
    admin_token = admin_verified.json()["access_token"]

    member_login = await client.post(
        "/api/v1/auth/login/password",
        json={"email": member.email, "password": "StrongPassword#2026"},
    )
    assert member_login.status_code == 200
    member_token = member_login.json()["access_token"]

    revoked = await client.post(
        f"/api/v1/auth/mfa/admin/users/{member.id}/revoke-sessions",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert revoked.status_code == 200
    assert revoked.json()["revoked_count"] == 1

    member_profile = await client.get(
        "/api/v1/org/me",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    admin_profile = await client.get(
        "/api/v1/org/me",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert member_profile.status_code == 401
    assert admin_profile.status_code == 200

    sessions = (
        await db_session.execute(
            select(UserSession).where(UserSession.user_id == member.id)
        )
    ).scalars().all()
    assert len(sessions) == 1
    assert sessions[0].revoke_reason == "revoked_by_institution_admin"
