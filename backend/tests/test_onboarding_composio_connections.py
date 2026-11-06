"""Onboarding auth config discovery and deny-by-default connection tests."""
from unittest.mock import AsyncMock
from types import SimpleNamespace

import pytest

from app.services.composio import client as composio_client
from app.services.composio import connections as connection_service
from app.services.composio.connections import ConnectionDenied


def test_onboarding_auth_configs_only_include_enabled_with_toolkit(monkeypatch):
    rows = [
        {"id": "ac_gmail", "toolkit": {"slug": "Gmail"}, "status": "ENABLED", "auth_scheme": "OAUTH2"},
        {"id": "ac_disabled", "toolkit": {"slug": "slack"}, "status": "DISABLED", "auth_scheme": "OAUTH2"},
        {"id": "ac_missing", "toolkit": {}, "status": "ENABLED", "auth_scheme": "OAUTH2"},
        {"id": "ac_key", "toolkit": {"slug": "stripe"}, "status": "ENABLED", "auth_scheme": "API_KEY"},
    ]
    fake = SimpleNamespace(auth_configs=SimpleNamespace(list=lambda **kwargs: {"items": rows}))
    monkeypatch.setattr(composio_client, "get_composio_client", lambda: fake)
    result = composio_client.list_onboarding_auth_configs()
    assert {entry["auth_config_id"] for entry in result} == {"ac_gmail", "ac_key"}
    assert next(item for item in result if item["auth_config_id"] == "ac_gmail")["toolkit_slug"] == "gmail"


@pytest.mark.asyncio
async def test_onboarding_connection_never_bypasses_global_allowlist(monkeypatch):
    monkeypatch.setattr(connection_service, "require_composio_configuration", lambda: object())
    monkeypatch.setattr(connection_service, "composio_toolkit_allowed", lambda slug: False)
    db = AsyncMock()
    with pytest.raises(ConnectionDenied, match="allowlist"):
        await connection_service.start_connect_link(
            db, tenant_id="tenant-a", actor_user_id="admin-a", toolkit_slug="gmail",
            auth_config_id="ac_gmail", require_tool_policy=False,
        )
    db.execute.assert_not_awaited()
