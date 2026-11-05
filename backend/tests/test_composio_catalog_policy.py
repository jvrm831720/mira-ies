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
        is_enabled=False,
        tool_slugs=[],
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



def test_composio_tool_selection_is_validated_against_toolkit(monkeypatch):
    from app.services.composio import client

    monkeypatch.setattr(
        client,
        "list_tools_for_toolkit",
        lambda _toolkit: [{"slug": "GMAIL_FETCH_EMAILS"}, {"slug": "GMAIL_CREATE_DRAFT"}],
    )
    assert client.validate_tool_slugs("gmail", ["gmail_fetch_emails"]) == ["GMAIL_FETCH_EMAILS"]
    with pytest.raises(ValueError, match="não pertencem"):
        client.validate_tool_slugs("gmail", ["SLACK_SEND_MESSAGE"])



def test_composio_endpoints_require_settings_manage_for_custom_roles():
    from starlette.requests import Request

    from app.core.auth import _permission_for_request

    request = Request({
        "type": "http",
        "method": "GET",
        "path": "/api/v1/integrations/composio/catalog",
        "headers": [],
        "query_string": b"",
        "server": ("test", 80),
        "client": ("test", 123),
        "scheme": "http",
    })
    assert _permission_for_request(request) == "settings.manage"



def test_composio_catalog_fetches_all_pages(monkeypatch):
    from app.services.composio import client

    class ToolkitClient:
        def __init__(self):
            self.calls = []

        def list(self, **kwargs):
            self.calls.append(kwargs)
            if kwargs["cursor"] is None:
                return {
                    "items": [{"slug": "gmail", "name": "Gmail"}],
                    "next_cursor": "page-2",
                }
            return {
                "items": [{"slug": "slack", "name": "Slack"}],
                "next_cursor": None,
            }

    class FakeClient:
        def __init__(self):
            self.toolkits = ToolkitClient()

    fake = FakeClient()
    monkeypatch.setattr(client, "get_composio_client", lambda: fake)

    catalog = client.list_toolkits()
    assert [item["slug"] for item in catalog] == ["gmail", "slack"]
    assert len(fake.toolkits.calls) == 2
    assert fake.toolkits.calls[1]["cursor"] == "page-2"
