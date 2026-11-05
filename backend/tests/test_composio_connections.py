from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.config import Settings
from app.models.composio_connection import TenantComposioOAuthState, TenantComposioToolkitPolicy
from app.services.composio import connections as connections_mod
from app.services.composio.connections import ConnectionDenied, complete_connect_callback
from app.services.composio.gateway import composio_toolkit_allowed


@pytest.mark.asyncio
async def test_start_connect_requires_enabled_policy(monkeypatch):
    settings = Settings(
        composio_enabled=True,
        composio_api_key="k",
        composio_identity_secret="secret-32-bytes-minimum-value-xx",
        composio_allowed_toolkits="gmail",
        composio_callback_url="https://app.example.com/integrations/composio/callback",
        app_env="production",
    )
    monkeypatch.setattr(connections_mod, "require_composio_configuration", lambda: settings)
    monkeypatch.setattr(connections_mod, "composio_toolkit_allowed", lambda slug: composio_toolkit_allowed(slug, settings))

    db = AsyncMock()
    # policy lookup returns None
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=result)

    with pytest.raises(ConnectionDenied, match="não habilitado"):
        await connections_mod.start_connect_link(
            db,
            tenant_id="t1",
            actor_user_id="u1",
            toolkit_slug="gmail",
            auth_config_id="ac_123",
        )


@pytest.mark.asyncio
async def test_complete_callback_rejects_foreign_or_expired_state(monkeypatch):
    settings = Settings(
        composio_enabled=True,
        composio_api_key="k",
        composio_identity_secret="secret-32-bytes-minimum-value-xx",
    )
    monkeypatch.setattr(connections_mod, "require_composio_configuration", lambda: settings)

    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=result)

    with pytest.raises(ConnectionDenied, match="inválido"):
        await complete_connect_callback(db, tenant_id="t1", state_token="missing")

    expired = TenantComposioOAuthState(
        tenant_id="t1",
        toolkit_slug="gmail",
        auth_config_id="ac",
        state_token="tok",
        status="pending",
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    result.scalar_one_or_none.return_value = expired
    with pytest.raises(ConnectionDenied, match="expirado"):
        await complete_connect_callback(db, tenant_id="t1", state_token="tok")


def test_global_allowlist_still_fail_closed():
    empty = Settings(composio_allowed_toolkits="")
    assert composio_toolkit_allowed("gmail", empty) is False
