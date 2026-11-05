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
