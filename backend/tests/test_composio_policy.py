from __future__ import annotations

import pytest

from app.services.composio import policy


def test_encrypted_arguments_round_trip_and_tenant_binding(monkeypatch):
    class Settings:
        secret_key = "s" * 48
        composio_identity_secret = "i" * 48

    monkeypatch.setattr(policy, "get_settings", lambda: Settings())
    arguments = {"query": "status", "count": 3}
    ciphertext = policy.encrypt_arguments(tenant_id="tenant-a", arguments=arguments)

    assert policy.decrypt_arguments(tenant_id="tenant-a", ciphertext=ciphertext) == arguments
    with pytest.raises(policy.ComposioPolicyDenied):
        policy.decrypt_arguments(tenant_id="tenant-b", ciphertext=ciphertext)


def test_redaction_masks_sensitive_keys_recursively():
    value = {
        "recipient": "person@example.com",
        "message": "hello",
        "nested": {"access_token": "secret", "count": 2},
    }

    assert policy.redact_arguments(value) == {
        "recipient": "[redacted]",
        "message": "hello",
        "nested": {"access_token": "[redacted]", "count": 2},
    }


def test_schema_validation_rejects_missing_required_and_unknown_fields():
    schema = {
        "type": "object",
        "properties": {"name": {"type": "string"}, "active": {"type": "boolean"}},
        "required": ["name"],
        "additionalProperties": False,
    }

    policy._validate_schema_value({"name": "Mira", "active": True}, schema)
    with pytest.raises(policy.ComposioPolicyDenied):
        policy._validate_schema_value({"active": True}, schema)
    with pytest.raises(policy.ComposioPolicyDenied):
        policy._validate_schema_value({"name": "Mira", "admin": True}, schema)


def test_schema_validation_fails_closed_on_unsupported_keywords():
    with pytest.raises(policy.ComposioPolicyDenied):
        policy._validate_schema_value(
            {"name": "Mira"},
            {"type": "object", "properties": {}, "patternProperties": {}},
        )


def test_approval_api_rejects_api_keys_and_requires_human_aal2():
    from types import SimpleNamespace

    from fastapi import HTTPException
    from app.api.composio import _require_human_aal2

    api_key = SimpleNamespace(user_id=None, session_id=None, aal=2)
    with pytest.raises(HTTPException) as exc:
        _require_human_aal2(api_key)
    assert exc.value.status_code == 403

    aal1 = SimpleNamespace(user_id="user-a", session_id="session-a", aal=1)
    with pytest.raises(HTTPException):
        _require_human_aal2(aal1)

    human = SimpleNamespace(user_id="user-a", session_id="session-a", aal=2)
    assert _require_human_aal2(human) is None


def test_approval_response_only_returns_redacted_decrypted_preview(monkeypatch):
    from datetime import datetime, timedelta, timezone
    from types import SimpleNamespace

    from app.api.composio import _approval_response

    class Settings:
        secret_key = "s" * 48
        composio_identity_secret = "i" * 48

    monkeypatch.setattr(policy, "get_settings", lambda: Settings())
    ciphertext = policy.encrypt_arguments(
        tenant_id="tenant-a",
        arguments={"recipient_email": "person@example.com", "subject": "Hello"},
    )
    now = datetime.now(timezone.utc)
    row = SimpleNamespace(
        id="approval-1", tenant_id="tenant-a",
        connected_account_id="ca-1", toolkit_slug="gmail",
        tool_slug="GMAIL_SEND_EMAIL", status="pending_approval",
        arguments_ciphertext=ciphertext, request_fingerprint="f" * 64,
        requested_by_user_id="user-a", reviewed_by_user_id=None,
        requested_at=now, expires_at=now + timedelta(minutes=30),
        reviewed_at=None,
    )

    result = _approval_response(row)
    assert result["arguments_preview"] == {
        "recipient_email": "[redacted]", "subject": "Hello"
    }
    assert "arguments_ciphertext" not in result
    assert "arguments" not in result



def test_redaction_masks_personal_values_even_under_generic_keys():
    value = {
        "destination": "contato@example.com",
        "notes": "CPF 123.456.789-00",
        "text": "Ligue +55 (21) 99999-1234",
    }

    preview = policy.redact_arguments(value)
    assert preview["destination"] == "[redacted]"
    assert preview["notes"] == "[redacted]"
    assert preview["text"] == "[redacted]"
