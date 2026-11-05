from __future__ import annotations

import pytest

from app.services.composio.client import _as_dict


def test_composio_sdk_model_normalization_supports_dict_and_model_dump():
    assert _as_dict({"slug": "gmail"}) == {"slug": "gmail"}

    class SDKModel:
        def model_dump(self):
            return {"slug": "slack", "name": "Slack"}

    assert _as_dict(SDKModel()) == {"slug": "slack", "name": "Slack"}


def test_composio_toolkit_policy_defaults_disabled_and_empty():
    from app.models.composio_connection import TenantComposioToolkitPolicy

    policy = TenantComposioToolkitPolicy(
        tenant_id="00000000-0000-0000-0000-000000000001",
        toolkit_slug="gmail",
    )
    assert policy.is_enabled is False
    assert policy.tool_slugs == []


def test_composio_catalog_adapter_is_fail_closed_without_configuration(monkeypatch):
    from app.core.config import Settings
    from app.services.composio import client

    monkeypatch.setattr(
        "app.services.composio.gateway.get_settings",
        lambda: Settings(composio_enabled=False),
    )
    with pytest.raises(Exception):
        client.list_toolkits()
