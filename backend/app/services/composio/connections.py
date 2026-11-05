"""Connect Link lifecycle and account registry for tenant-owned Composio accounts.

Credentials never enter MIRA. Only opaque IDs, status and anti-CSRF state are stored.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.composio_connection import (
    TenantComposioAccount,
    TenantComposioOAuthState,
    TenantComposioToolkitPolicy,
)
from app.services.composio.client import (
    create_connect_link,
    list_connected_accounts_for_user,
    revoke_connected_account,
)
from app.services.composio.gateway import composio_toolkit_allowed, require_composio_configuration
from app.services.composio.sessions import ensure_tenant_session

_OAUTH_STATE_TTL = timedelta(minutes=15)


class ConnectionDenied(RuntimeError):
    """Raised when policy or configuration forbids a connection action."""


def _normalize_toolkit(slug: str) -> str:
    value = (slug or "").strip().lower()
    if not value or len(value) > 80 or not value.replace("_", "").replace("-", "").isalnum():
        raise ValueError("Toolkit slug inválido.")
    return value


async def _require_enabled_toolkit_policy(
    db: AsyncSession,
    *,
    tenant_id: str,
    toolkit_slug: str,
) -> TenantComposioToolkitPolicy:
    if not composio_toolkit_allowed(toolkit_slug):
        raise ConnectionDenied("Toolkit não está na allowlist global do projeto.")
    result = await db.execute(
        select(TenantComposioToolkitPolicy).where(
            TenantComposioToolkitPolicy.tenant_id == tenant_id,
            TenantComposioToolkitPolicy.toolkit_slug == toolkit_slug,
        )
    )
    policy = result.scalar_one_or_none()
    if policy is None or not policy.is_enabled or not policy.tool_slugs:
        raise ConnectionDenied(
            "Toolkit não habilitado para esta instituição. Configure a policy antes de conectar."
        )
    return policy


async def start_connect_link(
    db: AsyncSession,
    *,
    tenant_id: str,
    actor_user_id: str | None,
    toolkit_slug: str,
    auth_config_id: str,
    callback_url: str | None = None,
) -> dict[str, Any]:
    """Create a one-time Connect Link after policy and allowlist checks."""
    settings = require_composio_configuration()
    slug = _normalize_toolkit(toolkit_slug)
    auth_cfg = (auth_config_id or "").strip()
    if not auth_cfg or len(auth_cfg) > 80:
        raise ValueError("auth_config_id inválido.")

    await _require_enabled_toolkit_policy(db, tenant_id=tenant_id, toolkit_slug=slug)
    session = await ensure_tenant_session(db, tenant_id=tenant_id, actor_user_id=actor_user_id)

    effective_callback = (callback_url or settings.composio_callback_url or "").strip() or None
    if effective_callback and not effective_callback.startswith("https://"):
        # Allow http only for local development callbacks.
        if not (
            settings.app_env == "development"
            and effective_callback.startswith("http://localhost")
        ):
            raise ValueError("callback_url deve ser HTTPS (ou localhost em development).")

    state_token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    oauth_state = TenantComposioOAuthState(
        tenant_id=tenant_id,
        toolkit_slug=slug,
        auth_config_id=auth_cfg,
        state_token=state_token,
        status="pending",
        created_by_user_id=actor_user_id,
        expires_at=now + _OAUTH_STATE_TTL,
    )
    db.add(oauth_state)
    await db.flush()

    # Append state to callback so the return path can bind the tenant safely.
    link_callback = effective_callback
    if link_callback:
        sep = "&" if "?" in link_callback else "?"
        link_callback = f"{link_callback}{sep}state={state_token}"

    link = create_connect_link(
        user_id=session.composio_user_id,
        auth_config_id=auth_cfg,
        callback_url=link_callback,
    )
    session.status = "active"
    session.updated_at = now
    await db.commit()

    return {
        "toolkit_slug": slug,
        "redirect_url": link.get("redirect_url"),
        "expires_at": oauth_state.expires_at.isoformat(),
        "state": state_token,
        "composio_user_id": session.composio_user_id,
    }


async def complete_connect_callback(
    db: AsyncSession,
    *,
    tenant_id: str,
    state_token: str,
    connected_account_id: str | None = None,
) -> dict[str, Any]:
    """Consume one-time state and register the connected account if provided."""
    require_composio_configuration()
    token = (state_token or "").strip()
    if not token:
        raise ValueError("state obrigatório.")

    result = await db.execute(
        select(TenantComposioOAuthState).where(
            TenantComposioOAuthState.tenant_id == tenant_id,
            TenantComposioOAuthState.state_token == token,
        )
    )
    row = result.scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if row is None:
        raise ConnectionDenied("State OAuth inválido para este tenant.")
    if row.status != "pending":
        raise ConnectionDenied("State OAuth já foi consumido ou expirou.")
    if row.expires_at.tzinfo is None or row.expires_at <= now:
        row.status = "expired"
        await db.commit()
        raise ConnectionDenied("State OAuth expirado.")

    row.status = "consumed"
    row.consumed_at = now

    account_payload: dict[str, Any] | None = None
    account_id = (connected_account_id or "").strip() or None
    if account_id:
        existing = await db.execute(
            select(TenantComposioAccount).where(
                TenantComposioAccount.tenant_id == tenant_id,
                TenantComposioAccount.connected_account_id == account_id,
            )
        )
        account = existing.scalar_one_or_none()
        if account is None:
            account = TenantComposioAccount(
                tenant_id=tenant_id,
                toolkit_slug=row.toolkit_slug,
                connected_account_id=account_id,
                auth_config_id=row.auth_config_id,
                status="active",
                connected_by_user_id=row.created_by_user_id,
                connected_at=now,
            )
            db.add(account)
        else:
            account.status = "active"
            account.disconnected_at = None
            account.auth_config_id = row.auth_config_id
            account.updated_at = now
        account_payload = {
            "connected_account_id": account.connected_account_id,
            "toolkit_slug": account.toolkit_slug,
            "status": account.status,
        }

    await db.commit()
    return {
        "ok": True,
        "toolkit_slug": row.toolkit_slug,
        "account": account_payload,
    }


async def list_tenant_accounts(
    db: AsyncSession,
    *,
    tenant_id: str,
    sync_remote: bool = False,
) -> list[dict[str, Any]]:
    """List accounts registered for the tenant; optionally refresh from Composio."""
    require_composio_configuration()
    session = await ensure_tenant_session(db, tenant_id=tenant_id, actor_user_id=None)

    if sync_remote:
        remote = list_connected_accounts_for_user(session.composio_user_id)
        by_id = {item["connected_account_id"]: item for item in remote if item.get("connected_account_id")}
        result = await db.execute(
            select(TenantComposioAccount).where(TenantComposioAccount.tenant_id == tenant_id)
        )
        local_rows = {row.connected_account_id: row for row in result.scalars().all()}
        now = datetime.now(timezone.utc)
        for account_id, remote_item in by_id.items():
            local = local_rows.get(account_id)
            status = (remote_item.get("status") or "active").lower()
            if status not in {"active", "expired", "revoked", "error"}:
                status = "active"
            toolkit = (remote_item.get("toolkit_slug") or "unknown").lower()
            if local is None:
                db.add(
                    TenantComposioAccount(
                        tenant_id=tenant_id,
                        toolkit_slug=toolkit[:80],
                        connected_account_id=account_id,
                        auth_config_id=remote_item.get("auth_config_id"),
                        display_name=remote_item.get("display_name"),
                        status=status,
                        connected_at=now,
                    )
                )
            else:
                local.status = status
                local.display_name = remote_item.get("display_name") or local.display_name
                local.auth_config_id = remote_item.get("auth_config_id") or local.auth_config_id
                local.updated_at = now
        await db.commit()

    result = await db.execute(
        select(TenantComposioAccount)
        .where(TenantComposioAccount.tenant_id == tenant_id)
        .order_by(TenantComposioAccount.connected_at.desc())
    )
    return [
        {
            "id": row.id,
            "toolkit_slug": row.toolkit_slug,
            "connected_account_id": row.connected_account_id,
            "auth_config_id": row.auth_config_id,
            "display_name": row.display_name,
            "status": row.status,
            "connected_at": row.connected_at.isoformat() if row.connected_at else None,
            "disconnected_at": row.disconnected_at.isoformat() if row.disconnected_at else None,
        }
        for row in result.scalars().all()
    ]


async def revoke_tenant_account(
    db: AsyncSession,
    *,
    tenant_id: str,
    connected_account_id: str,
    revoke_remote: bool = True,
) -> dict[str, Any]:
    require_composio_configuration()
    account_id = (connected_account_id or "").strip()
    if not account_id:
        raise ValueError("connected_account_id obrigatório.")

    result = await db.execute(
        select(TenantComposioAccount).where(
            TenantComposioAccount.tenant_id == tenant_id,
            TenantComposioAccount.connected_account_id == account_id,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise ConnectionDenied("Conta conectada não encontrada neste tenant.")

    if revoke_remote:
        try:
            revoke_connected_account(account_id)
        except Exception:
            # Still mark local as revoked so policy stays fail-closed.
            pass

    now = datetime.now(timezone.utc)
    row.status = "revoked"
    row.disconnected_at = now
    row.updated_at = now
    await db.commit()
    return {
        "connected_account_id": row.connected_account_id,
        "toolkit_slug": row.toolkit_slug,
        "status": row.status,
        "disconnected_at": row.disconnected_at.isoformat(),
    }
