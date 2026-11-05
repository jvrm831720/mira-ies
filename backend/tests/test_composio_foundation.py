from __future__ import annotations

import json

import pytest
from fastapi import HTTPException

from app.api.composio import _auth_configs
from app.services.composio.client import ComposioClient, ComposioNotConfigured


def test_composio_client_requires_api_key():
    with pytest.raises(ComposioNotConfigured):
        ComposioClient(api_key="")


def test_auth_config_map_is_server_side(monkeypatch):
    from app.core.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("COMPOSIO_AUTH_CONFIGS_JSON", json.dumps({"google_drive": "ac_test"}))
    assert _auth_configs() == {"google_drive": "ac_test"}
    get_settings.cache_clear()


def test_auth_config_map_rejects_non_object(monkeypatch):
    from app.core.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("COMPOSIO_AUTH_CONFIGS_JSON", "[]")
    with pytest.raises(HTTPException) as error:
        _auth_configs()
    assert error.value.status_code == 503
    get_settings.cache_clear()
