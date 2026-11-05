from __future__ import annotations

from app.core.config import Settings
from app.services.composio.gateway import (
    ComposioNotConfigured,
    composio_is_configured,
    composio_toolkit_allowed,
    require_composio_configuration,
)
from app.services.composio.identity import composio_user_id_for_tenant


def test_composio_tenant_identity_is_stable_and_opaque(monkeypatch):
    from app.services.composio import identity

    settings = Settings(secret_key="test-composio-identity-secret-32-bytes")
    monkeypatch.setattr(identity, "get_settings", lambda: settings)

    first = composio_user_id_for_tenant("tenant-uuid-a")
    assert first == composio_user_id_for_tenant("tenant-uuid-a")
    assert first != composio_user_id_for_tenant("tenant-uuid-b")
    assert first.startswith("mira_tenant_")
    assert "tenant-uuid-a" not in first
    assert "@" not in first


def test_composio_is_disabled_by_default():
    settings = Settings()
    assert settings.composio_enabled is False
    assert composio_is_configured(settings) is False


def test_composio_requires_both_explicit_enablement_and_api_key():
    disabled = Settings(composio_enabled=False, composio_api_key="test-key")
    enabled_without_key = Settings(composio_enabled=True, composio_api_key=None)
    enabled = Settings(composio_enabled=True, composio_api_key="test-key")

    assert composio_is_configured(disabled) is False
    assert composio_is_configured(enabled_without_key) is False
    assert composio_is_configured(enabled) is True


def test_composio_gateway_fails_closed_until_configured():
    settings = Settings(composio_enabled=False, composio_api_key=None)
    try:
        require_composio_configuration(settings)
    except ComposioNotConfigured as exc:
        assert "desativado" in str(exc)
    else:
        raise AssertionError("Composio não configurado deveria falhar fechado")


def test_composio_toolkit_allowlist_fails_closed():
    empty = Settings(composio_allowed_toolkits="")
    allowlisted = Settings(composio_allowed_toolkits="gmail, google_drive")

    assert composio_toolkit_allowed("gmail", empty) is False
    assert composio_toolkit_allowed("GMAIL", allowlisted) is True
    assert composio_toolkit_allowed("google_drive", allowlisted) is True
    assert composio_toolkit_allowed("slack", allowlisted) is False
    assert composio_toolkit_allowed("", allowlisted) is False
