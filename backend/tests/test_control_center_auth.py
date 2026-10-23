from types import SimpleNamespace

from app.api import control_center_auth as auth


def test_control_center_token_has_separate_audience(monkeypatch):
    monkeypatch.setattr(auth, "get_settings", lambda: SimpleNamespace(secret_key="test-secret-key-at-least-32-chars"))
    admin = SimpleNamespace(id="admin-123", role="finance", auth_version=3)
    token = auth._issue_token(admin)
    claims = auth._decode_token(token)
    assert claims is not None
    assert claims["iss"] == "mira-control-center"
    assert claims["aud"] == "mira-control-center"
    assert claims["sub"] == "admin-123"
    assert claims["role"] == "finance"
    assert claims["ver"] == 3


def test_control_center_rejects_customer_token_audience(monkeypatch):
    monkeypatch.setattr(auth, "get_settings", lambda: SimpleNamespace(secret_key="test-secret-key-at-least-32-chars"))
    import base64
    import hashlib
    import hmac
    import json
    import time

    def enc(value):
        return base64.urlsafe_b64encode(value).rstrip(b"=").decode()
    header = enc(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    claims = enc(json.dumps({
        "iss": "mira", "aud": "customer-app", "sub": "customer-1",
        "iat": int(time.time()), "exp": int(time.time()) + 60,
    }, separators=(",", ":")).encode())
    unsigned = f"{header}.{claims}"
    sig = enc(hmac.new(b"test-secret-key-at-least-32-chars", unsigned.encode(), hashlib.sha256).digest())
    assert auth._decode_token(f"{unsigned}.{sig}") is None


def test_email_mfa_digest_is_bound_to_email_and_code(monkeypatch):
    monkeypatch.setattr(auth, "get_settings", lambda: SimpleNamespace(secret_key="test-secret-key-at-least-32-chars"))
    first = auth._digest("otp", "admin@example.com:123456")
    assert first == auth._digest("otp", "admin@example.com:123456")
    assert first != auth._digest("otp", "admin@example.com:123457")
    assert first != auth._digest("otp", "other@example.com:123456")


def test_rbac_roles_do_not_grant_finance_to_support():
    assert "billing:write" not in auth._ROLE_PERMISSIONS["support"]
    assert "billing:write" in auth._ROLE_PERMISSIONS["finance"]
    assert "*" in auth._ROLE_PERMISSIONS["super_admin"]



def test_billing_record_requires_https_payment_link():
    import pytest
    from datetime import datetime, timezone
    from pydantic import ValidationError
    from app.api.control_center_admin import BillingRecordCreate

    base = {
        "tenant_id": "9c78bde7-52d3-4c45-9f5a-8c6d3b29d71a",
        "plan_name": "MIRA Growth",
        "plan_price_brl": 497,
        "due_at": datetime.now(timezone.utc).isoformat(),
    }
    accepted = BillingRecordCreate(**base, payment_link="https://pay.example.com/checkout")
    assert accepted.payment_link == "https://pay.example.com/checkout"
    with pytest.raises(ValidationError):
        BillingRecordCreate(**base, payment_link="http://pay.example.com/checkout")


def test_billing_record_rejects_invalid_tenant_id():
    import pytest
    from datetime import datetime, timezone
    from pydantic import ValidationError
    from app.api.control_center_admin import BillingRecordCreate

    with pytest.raises(ValidationError):
        BillingRecordCreate(
            tenant_id="not-a-uuid",
            plan_name="MIRA Growth",
            plan_price_brl=497,
            due_at=datetime.now(timezone.utc).isoformat(),
        )



def test_malformed_control_center_tokens_are_rejected_without_exception():
    for token in ("", "not-a-token", "...", "....", "%%%.%%%.%%%", "a.b.c"):
        assert auth._decode_token(token) is None



def test_only_super_admin_can_write_organizations_and_members():
    write_permissions = {"orgs:write", "members:write"}
    for role in ("operations", "finance", "support", "auditor"):
        assert write_permissions.isdisjoint(auth._ROLE_PERMISSIONS[role])
    assert "*" in auth._ROLE_PERMISSIONS["super_admin"]



def test_rate_limit_supports_per_account_identity_without_forwarded_ip(monkeypatch):
    import asyncio

    keys = []
    class FakeRedis:
        async def incr(self, key):
            keys.append(key)
            return 1
        async def expire(self, key, seconds):
            return True
        async def aclose(self):
            return None

    monkeypatch.setattr(
        auth, "get_settings",
        lambda: SimpleNamespace(secret_key="test-secret-key-at-least-32-chars", redis_url="redis://localhost"),
    )
    monkeypatch.setattr(auth.Redis, "from_url", lambda *args, **kwargs: FakeRedis())
    request = SimpleNamespace(client=SimpleNamespace(host="frontend-bff"))

    async def run():
        await auth._enforce_rate_limit(request, "login_email", 10, 300, identity="admin-a@example.com")
        await auth._enforce_rate_limit(request, "login_email", 10, 300, identity="admin-b@example.com")

    asyncio.run(run())
    assert len(set(keys)) == 2
    assert keys[0] != keys[1]



def test_control_center_token_expiration_is_enforced(monkeypatch):
    import time

    monkeypatch.setattr(auth, "get_settings", lambda: SimpleNamespace(secret_key="test-secret-key-at-least-32-chars"))
    admin = SimpleNamespace(id="admin-expiry", role="auditor", auth_version=0)
    token = auth._issue_token(admin)
    real_time = time.time()
    monkeypatch.setattr(auth.time, "time", lambda: real_time + 21 * 60)
    assert auth._decode_token(token) is None


def test_rate_limit_fails_closed_when_redis_is_unavailable(monkeypatch):
    import asyncio
    import pytest
    from fastapi import HTTPException

    class BrokenRedis:
        async def incr(self, _key):
            raise RuntimeError("redis offline")
        async def aclose(self):
            return None

    monkeypatch.setattr(
        auth, "get_settings",
        lambda: SimpleNamespace(secret_key="test-secret-key-at-least-32-chars", redis_url="redis://localhost"),
    )
    monkeypatch.setattr(auth.Redis, "from_url", lambda *args, **kwargs: BrokenRedis())
    request = SimpleNamespace(client=SimpleNamespace(host="shared-bff"))

    with pytest.raises(HTTPException) as exc:
        asyncio.run(auth._enforce_rate_limit(request, "login_email", 10, 300, identity="admin@example.com"))
    assert exc.value.status_code == 503


def test_admin_permission_rejects_missing_credentials_and_denies_wrong_role(monkeypatch):
    import asyncio
    import pytest
    from fastapi import HTTPException

    monkeypatch.setattr(auth, "get_settings", lambda: SimpleNamespace(secret_key="test-secret-key-at-least-32-chars"))

    class FakeDB:
        def __init__(self, admin):
            self.admin = admin
        async def get(self, _model, _admin_id):
            return self.admin

    with pytest.raises(HTTPException) as missing:
        asyncio.run(auth.require_admin_permission("orgs:read", None, FakeDB(None)))
    assert missing.value.status_code == 401

    admin = SimpleNamespace(id="support-1", role="support", auth_version=0, is_active=True)
    token = auth._issue_token(admin)
    with pytest.raises(HTTPException) as denied:
        asyncio.run(auth.require_admin_permission("orgs:write", SimpleNamespace(credentials=token), FakeDB(admin)))
    assert denied.value.status_code == 403

    allowed = asyncio.run(
        auth.require_admin_permission("orgs:read", SimpleNamespace(credentials=token), FakeDB(admin))
    )
    assert allowed.id == "support-1"


def test_mfa_code_is_single_use_and_replay_is_rejected(monkeypatch):
    import asyncio
    from datetime import timedelta
    import pytest
    from fastapi import HTTPException

    monkeypatch.setattr(auth, "get_settings", lambda: SimpleNamespace(secret_key="test-secret-key-at-least-32-chars"))
    admin = SimpleNamespace(id="admin-1", email="admin@example.com", is_active=True, role="super_admin", auth_version=0)
    challenge = SimpleNamespace(
        id="challenge-1",
        admin_id=admin.id,
        email_hash=auth._digest("email", admin.email),
        code_hash=auth._digest("otp", f"{admin.email}:123456"),
        expires_at=auth._now() + timedelta(minutes=5),
        consumed_at=None,
        attempts=0,
    )

    class Result:
        def scalar_one_or_none(self):
            return None if challenge.consumed_at else challenge

    class FakeDB:
        async def execute(self, _query):
            return Result()
        async def get(self, _model, _admin_id):
            return admin
        async def commit(self):
            return None

    async def no_limit(*args, **kwargs):
        return None
    async def no_audit(*args, **kwargs):
        return None

    monkeypatch.setattr(auth, "_enforce_rate_limit", no_limit)
    monkeypatch.setattr(auth, "_audit", no_audit)
    request = SimpleNamespace(headers={}, url=SimpleNamespace(path="/api/v1/admin/control-center/auth/verify"), method="POST")
    body = auth.VerifyEmailCodePayload(email=admin.email, code="123456")
    db = FakeDB()

    session = asyncio.run(auth.verify_admin_email_code(body, request, db))
    assert session.role == "super_admin"
    assert challenge.consumed_at is not None
    with pytest.raises(HTTPException) as replay:
        asyncio.run(auth.verify_admin_email_code(body, request, db))
    assert replay.value.status_code == 401


def test_mfa_expired_code_is_rejected(monkeypatch):
    import asyncio
    from datetime import timedelta
    import pytest
    from fastapi import HTTPException

    monkeypatch.setattr(auth, "get_settings", lambda: SimpleNamespace(secret_key="test-secret-key-at-least-32-chars"))
    email = "admin@example.com"
    challenge = SimpleNamespace(
        id="challenge-expired", admin_id="admin-1",
        email_hash=auth._digest("email", email),
        code_hash=auth._digest("otp", f"{email}:123456"),
        expires_at=auth._now() - timedelta(seconds=1), consumed_at=None, attempts=0,
    )
    class Result:
        def scalar_one_or_none(self):
            return None if challenge.consumed_at else challenge
    class FakeDB:
        async def execute(self, _query):
            return Result()
        async def commit(self):
            return None
    async def no_limit(*args, **kwargs):
        return None
    async def no_audit(*args, **kwargs):
        return None
    monkeypatch.setattr(auth, "_enforce_rate_limit", no_limit)
    monkeypatch.setattr(auth, "_audit", no_audit)
    request = SimpleNamespace(headers={}, url=SimpleNamespace(path="/auth/verify"), method="POST")
    body = auth.VerifyEmailCodePayload(email=email, code="123456")

    with pytest.raises(HTTPException) as expired:
        asyncio.run(auth.verify_admin_email_code(body, request, FakeDB()))
    assert expired.value.status_code == 401
    assert challenge.consumed_at is not None



def test_audit_metadata_exposes_only_allowlisted_before_after_fields():
    from app.api.control_center_admin import _safe_audit_metadata

    metadata = {
        "fields_updated": ["is_active", "role", "password_hash", {"unexpected": True}],
        "before": {"is_active": True, "role": "admin", "password_hash": "never-expose"},
        "after": {"is_active": False, "role": "viewer", "password_hash": "secret"},
    }
    result = _safe_audit_metadata("member_updated", metadata)
    assert result == {
        "fields_updated": ["is_active", "role"],
        "before": {"is_active": True, "role": "admin"},
        "after": {"is_active": False, "role": "viewer"},
    }
    assert "password_hash" not in str(result)


def test_audit_metadata_omits_unreviewed_actions_and_billing_notes():
    from app.api.control_center_admin import _safe_audit_metadata

    assert _safe_audit_metadata("unknown_action", {"secret": "do-not-return"}) is None
    assert _safe_audit_metadata(
        "billing_record_updated",
        {"fields_updated": ["notes", "payment_status", "payment_link"]},
    ) == {"fields_updated": ["payment_status"]}



def test_http_permission_boundary_returns_403_for_non_super_admin(monkeypatch):
    from fastapi import Depends, FastAPI
    from fastapi.testclient import TestClient

    monkeypatch.setattr(auth, "get_settings", lambda: SimpleNamespace(secret_key="test-secret-key-at-least-32-chars"))
    admin = SimpleNamespace(id="support-1", role="support", auth_version=0, is_active=True)

    class FakeDB:
        async def get(self, _model, _admin_id):
            return admin

    async def override_db():
        return FakeDB()

    app = FastAPI()
    app.dependency_overrides[auth.get_db] = override_db

    @app.patch("/protected")
    async def protected(_admin=Depends(auth.admin_permission("orgs:write"))):
        return {"ok": True}

    token = auth._issue_token(admin)
    response = TestClient(app).patch("/protected", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403
    assert response.json()["detail"] == "Permissão insuficiente."


def test_login_email_provider_failure_consumes_mfa_challenge(monkeypatch):
    import asyncio
    import pytest
    from fastapi import HTTPException

    monkeypatch.setattr(
        auth, "get_settings",
        lambda: SimpleNamespace(
            secret_key="test-secret-key-at-least-32-chars",
            redis_url="redis://localhost",
            resend_api_key="resend-test-key",
            email_from="security@example.com",
        ),
    )
    monkeypatch.setattr(auth, "verify_password", lambda _password, _hashed: True)

    admin = SimpleNamespace(
        id="admin-email-fail", email="admin@example.com", display_name="Admin",
        password_hash="hash", is_active=True, role="super_admin", auth_version=0,
        failed_login_attempts=0, locked_until=None,
    )
    challenges = []
    execute_count = 0

    class Result:
        def __init__(self, value=None):
            self.value = value
        def scalar_one_or_none(self):
            return self.value

    class FakeDB:
        async def execute(self, _query):
            nonlocal execute_count
            execute_count += 1
            if execute_count == 1:
                return Result(admin)
            if execute_count == 2:
                return Result(None)
            return Result(None)
        def add(self, value):
            if isinstance(value, auth.AdminEmailChallenge):
                challenges.append(value)
        async def commit(self):
            return None

    async def no_limit(*args, **kwargs):
        return None
    async def no_audit(*args, **kwargs):
        return None
    async def failed_delivery(**kwargs):
        return SimpleNamespace(ok=False)

    monkeypatch.setattr(auth, "_enforce_rate_limit", no_limit)
    monkeypatch.setattr(auth, "_audit", no_audit)
    monkeypatch.setattr(auth, "send_email_resend", failed_delivery)
    request = SimpleNamespace(
        headers={}, url=SimpleNamespace(path="/api/v1/admin/control-center/auth/login"), method="POST"
    )

    with pytest.raises(HTTPException) as failure:
        asyncio.run(auth.start_admin_login(auth.PasswordPayload(email=admin.email, password="valid"), request, FakeDB()))
    assert failure.value.status_code == 503
    assert challenges and challenges[0].consumed_at is not None



def test_mfa_attempt_limit_consumes_challenge(monkeypatch):
    import asyncio
    from datetime import timedelta
    import pytest
    from fastapi import HTTPException

    monkeypatch.setattr(auth, "get_settings", lambda: SimpleNamespace(secret_key="test-secret-key-at-least-32-chars"))
    email = "admin@example.com"
    challenge = SimpleNamespace(
        id="challenge-attempt-limit", admin_id="admin-1",
        email_hash=auth._digest("email", email),
        code_hash=auth._digest("otp", f"{email}:123456"),
        expires_at=auth._now() + timedelta(minutes=5), consumed_at=None, attempts=4,
    )
    class Result:
        def scalar_one_or_none(self):
            return None if challenge.consumed_at else challenge
    class FakeDB:
        async def execute(self, _query):
            return Result()
        async def commit(self):
            return None
    async def no_limit(*args, **kwargs):
        return None
    async def no_audit(*args, **kwargs):
        return None
    monkeypatch.setattr(auth, "_enforce_rate_limit", no_limit)
    monkeypatch.setattr(auth, "_audit", no_audit)
    request = SimpleNamespace(headers={}, url=SimpleNamespace(path="/auth/verify"), method="POST")
    body = auth.VerifyEmailCodePayload(email=email, code="999999")

    with pytest.raises(HTTPException) as invalid:
        asyncio.run(auth.verify_admin_email_code(body, request, FakeDB()))
    assert invalid.value.status_code == 401
    assert challenge.attempts == 5
    assert challenge.consumed_at is not None


def test_admin_session_version_change_revokes_existing_token(monkeypatch):
    import asyncio
    import pytest
    from fastapi import HTTPException

    monkeypatch.setattr(auth, "get_settings", lambda: SimpleNamespace(secret_key="test-secret-key-at-least-32-chars"))
    admin = SimpleNamespace(id="admin-revoked", role="super_admin", auth_version=0, is_active=True)
    token = auth._issue_token(admin)
    admin.auth_version = 1

    class FakeDB:
        async def get(self, _model, _admin_id):
            return admin

    with pytest.raises(HTTPException) as revoked:
        asyncio.run(auth.require_admin_permission("orgs:read", SimpleNamespace(credentials=token), FakeDB()))
    assert revoked.value.status_code == 401
