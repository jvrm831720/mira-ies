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
