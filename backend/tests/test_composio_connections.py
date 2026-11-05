from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.config import Settings
from app.models.composio_connection import TenantComposioAccount, TenantComposioOAuthState
from app.services.composio import connections as connections_mod
from app.services.composio.connections import (
    ConnectionDenied,
    _server_callback_url,
    complete_connect_callback,
    revoke_tenant_account,
)
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
    monkeypatch.setattr(
        connections_mod, "composio_toolkit_allowed", lambda slug: composio_toolkit_allowed(slug, settings)
    )

    db = AsyncMock()
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


def test_server_callback_url_rejects_arbitrary_and_http_production():
    prod = Settings(
        composio_callback_url="http://evil.example/cb",
        app_env="production",
    )
    with pytest.raises(ValueError, match="HTTPS"):
        _server_callback_url(prod)

    missing = Settings(composio_callback_url=None, app_env="production")
    with pytest.raises(ValueError, match="não configurado"):
        _server_callback_url(missing)

    ok = Settings(
        composio_callback_url="https://app.example.com/cb",
        app_env="production",
    )
    assert _server_callback_url(ok).startswith("https://")

    dev = Settings(
        composio_callback_url="http://localhost:3000/cb",
        app_env="development",
    )
    assert "localhost" in _server_callback_url(dev)


@pytest.mark.asyncio
async def test_complete_rejects_missing_expired_and_foreign_account(monkeypatch):
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
        await complete_connect_callback(
            db, tenant_id="t1", state_token="missing", connected_account_id="ca_1"
        )

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
        await complete_connect_callback(
            db, tenant_id="t1", state_token="tok", connected_account_id="ca_1"
        )


@pytest.mark.asyncio
async def test_complete_verifies_remote_ownership(monkeypatch):
    settings = Settings(
        composio_enabled=True,
        composio_api_key="k",
        composio_identity_secret="secret-32-bytes-minimum-value-xx",
    )
    monkeypatch.setattr(connections_mod, "require_composio_configuration", lambda: settings)

    pending = TenantComposioOAuthState(
        tenant_id="t1",
        toolkit_slug="gmail",
        auth_config_id="ac",
        state_token="tok",
        status="pending",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        created_by_user_id="u1",
    )
    session = MagicMock()
    session.composio_user_id = "mira_tenant_abc"

    db = AsyncMock()
    state_result = MagicMock()
    state_result.scalar_one_or_none.return_value = pending
    account_result = MagicMock()
    account_result.scalar_one_or_none.return_value = None

    async def _execute(stmt):
        # First call: state FOR UPDATE; later: account lookup
        if "tenant_composio_oauth_states" in str(stmt) or pending.status == "pending":
            # simplified: always return state first then account
            if getattr(_execute, "calls", 0) == 0:
                _execute.calls = 1
                return state_result
            return account_result
        return account_result

    _execute.calls = 0
    db.execute = AsyncMock(side_effect=_execute)
    db.flush = AsyncMock()
    db.commit = AsyncMock()

    monkeypatch.setattr(
        connections_mod,
        "ensure_tenant_session",
        AsyncMock(return_value=session),
    )
    monkeypatch.setattr(
        connections_mod,
        "get_connected_account",
        lambda _id: {
            "connected_account_id": "ca_foreign",
            "user_id": "other_user",
            "toolkit_slug": "gmail",
            "status": "active",
        },
    )

    with pytest.raises(ConnectionDenied, match="não pertence"):
        await complete_connect_callback(
            db, tenant_id="t1", state_token="tok", connected_account_id="ca_foreign"
        )


@pytest.mark.asyncio
async def test_revoke_reports_remote_failure_honestly(monkeypatch):
    settings = Settings(
        composio_enabled=True,
        composio_api_key="k",
        composio_identity_secret="secret-32-bytes-minimum-value-xx",
    )
    monkeypatch.setattr(connections_mod, "require_composio_configuration", lambda: settings)
    monkeypatch.setattr(
        connections_mod,
        "revoke_connected_account",
        lambda _id: (_ for _ in ()).throw(RuntimeError("remote down")),
    )

    account = TenantComposioAccount(
        tenant_id="t1",
        toolkit_slug="gmail",
        connected_account_id="ca_1",
        status="active",
        account_metadata={},
    )
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = account
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()

    out = await revoke_tenant_account(
        db, tenant_id="t1", connected_account_id="ca_1", revoke_remote=True
    )
    assert out["local_disabled"] is True
    assert out["remote_status"] == "failed"
    assert out["status"] == "error"


def test_global_allowlist_still_fail_closed():
    empty = Settings(composio_allowed_toolkits="")
    assert composio_toolkit_allowed("gmail", empty) is False
