"""Connect Link lifecycle and account registry for tenant-owned Composio accounts.

Credentials never enter MIRA. Only opaque IDs, status and anti-CSRF state are stored.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.composio_approval import TenantComposioToolApproval
from app.models.composio_connection import TenantComposioToolAudit
from app.models.composio_connection import (
    TenantComposioAccount,
    TenantComposioOAuthState,
    TenantComposioToolkitPolicy,
)
from app.services.composio.client import (
    create_connect_link,
    get_connected_account,
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


def _server_callback_url(settings) -> str:
    """Only server-configured callback is allowed — never client-supplied URLs."""
    configured = (settings.composio_callback_url or "").strip()
    if not configured:
        raise ValueError("COMPOSIO_CALLBACK_URL não configurado no backend.")
    parsed = urlparse(configured)
    if parsed.scheme == "https" and parsed.netloc:
        return configured
    if (
        settings.app_env == "development"
        and parsed.scheme == "http"
        and parsed.hostname in {"localhost", "127.0.0.1"}
    ):
        return configured
    raise ValueError("COMPOSIO_CALLBACK_URL deve ser HTTPS (ou localhost em development).")


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


def _verify_remote_account(
    *,
    connected_account_id: str,
    expected_user_id: str,
    expected_toolkit: str,
) -> dict[str, Any]:
    """Confirm the account exists at Composio and belongs to this tenant identity."""
    remote = get_connected_account(connected_account_id)
    if remote is None:
        # Fallback: list by user and match id (some SDK versions lack get-by-id).
        for item in list_connected_accounts_for_user(expected_user_id):
            if item.get("connected_account_id") == connected_account_id:
                remote = item
                break
    if remote is None:
        raise ConnectionDenied("Conta conectada não encontrada na Composio.")

    remote_user = remote.get("user_id")
    if remote_user and remote_user != expected_user_id:
        raise ConnectionDenied("Conta conectada não pertence à identidade deste tenant.")

    # When user_id is absent on the object, require the account to appear in the user's list.
    if not remote_user:
        owned_ids = {
            item["connected_account_id"]
            for item in list_connected_accounts_for_user(expected_user_id)
        }
        if connected_account_id not in owned_ids:
            raise ConnectionDenied("Conta conectada não pertence à identidade deste tenant.")

    remote_toolkit = (remote.get("toolkit_slug") or "").lower()
    if remote_toolkit and remote_toolkit != expected_toolkit:
        raise ConnectionDenied("Toolkit da conta remota diverge do toolkit autorizado no state.")

    status = (remote.get("status") or "active").lower()
    if status in {"revoked", "expired", "disabled"}:
        raise ConnectionDenied(f"Conta remota não está ativa (status={status}).")

    return remote



async def _cancel_pending_approvals_for_account(
    db: AsyncSession,
    *,
    tenant_id: str,
    connected_account_id: str,
    actor_user_id: str | None = None,
) -> int:
    result = await db.execute(
        select(TenantComposioToolApproval)
        .where(
            TenantComposioToolApproval.tenant_id == tenant_id,
            TenantComposioToolApproval.connected_account_id == connected_account_id,
            TenantComposioToolApproval.status == "pending_approval",
        )
        .with_for_update()
    )
    rows = result.scalars().all()
    now = datetime.now(timezone.utc)
    for approval in rows:
        approval.status = "cancelled"
        db.add(TenantComposioToolAudit(
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            connected_account_id=connected_account_id,
            toolkit_slug=approval.toolkit_slug,
            tool_slug=approval.tool_slug,
            status="pending_approval",
            approval_required=True,
            approval_status="cancelled",
            request_fingerprint=approval.request_fingerprint,
            created_at=now,
        ))
    return len(rows)


async def start_connect_link(
    db: AsyncSession,
    *,
    tenant_id: str,
    actor_user_id: str | None,
    toolkit_slug: str,
    auth_config_id: str,
) -> dict[str, Any]:
    """Create a one-time Connect Link after policy and allowlist checks."""
    settings = require_composio_configuration()
    slug = _normalize_toolkit(toolkit_slug)
    auth_cfg = (auth_config_id or "").strip()
    if not auth_cfg or len(auth_cfg) > 80:
        raise ValueError("auth_config_id inválido.")

    await _require_enabled_toolkit_policy(db, tenant_id=tenant_id, toolkit_slug=slug)
    session = await ensure_tenant_session(db, tenant_id=tenant_id, actor_user_id=actor_user_id)

    callback_base = _server_callback_url(settings)
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

    sep = "&" if "?" in callback_base else "?"
    link_callback = f"{callback_base}{sep}state={state_token}"

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
    connected_account_id: str,
) -> dict[str, Any]:
    """Atomically consume state and register account only after remote verification."""
    require_composio_configuration()
    token = (state_token or "").strip()
    account_id = (connected_account_id or "").strip()
    if not token:
        raise ValueError("state obrigatório.")
    if not account_id:
        raise ValueError("connected_account_id obrigatório.")

    # Atomic claim: lock the row so concurrent completes cannot both succeed.
    result = await db.execute(
        select(TenantComposioOAuthState)
        .where(
            TenantComposioOAuthState.tenant_id == tenant_id,
            TenantComposioOAuthState.state_token == token,
        )
        .with_for_update()
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

    # Mark consumed before external verification so the token cannot be replayed.
    row.status = "consumed"
    row.consumed_at = now
    await db.flush()

    session = await ensure_tenant_session(db, tenant_id=tenant_id, actor_user_id=row.created_by_user_id)
    try:
        remote = _verify_remote_account(
            connected_account_id=account_id,
            expected_user_id=session.composio_user_id,
            expected_toolkit=row.toolkit_slug,
        )
    except ConnectionDenied:
        row.status = "failed"
        await db.commit()
        raise

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
            display_name=remote.get("display_name"),
            status="active",
            connected_by_user_id=row.created_by_user_id,
            connected_at=now,
        )
        db.add(account)
    else:
        account.status = "active"
        account.disconnected_at = None
        account.auth_config_id = row.auth_config_id
        account.display_name = remote.get("display_name") or account.display_name
        account.updated_at = now

    await db.commit()
    return {
        "ok": True,
        "toolkit_slug": row.toolkit_slug,
        "account": {
            "connected_account_id": account.connected_account_id,
            "toolkit_slug": account.toolkit_slug,
            "status": account.status,
            "verified_remote": True,
        },
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
                if status != "active":
                    await _cancel_pending_approvals_for_account(
                        db, tenant_id=tenant_id, connected_account_id=account_id
                    )
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
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    """Disable local use immediately; report remote revoke status honestly."""
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

    remote_status = "skipped"
    remote_error: str | None = None
    if revoke_remote:
        try:
            revoke_connected_account(account_id)
            remote_status = "revoked"
        except Exception as exc:
            remote_status = "failed"
            remote_error = type(exc).__name__

    # Local always blocked so agents cannot use the account even if remote revoke failed.
    now = datetime.now(timezone.utc)
    row.status = "revoked" if remote_status == "revoked" else "error"
    row.disconnected_at = now
    row.updated_at = now
    # Preserve a non-secret breadcrumb of remote outcome in metadata.
    meta = dict(row.account_metadata or {})
    meta["last_revoke"] = {
        "remote_status": remote_status,
        "at": now.isoformat(),
        "error": remote_error,
    }
    row.account_metadata = meta
    await _cancel_pending_approvals_for_account(
        db, tenant_id=tenant_id, connected_account_id=account_id,
        actor_user_id=actor_user_id,
    )
    await db.commit()

    return {
        "connected_account_id": row.connected_account_id,
        "toolkit_slug": row.toolkit_slug,
        "status": row.status,
        "local_disabled": True,
        "remote_status": remote_status,
        "disconnected_at": row.disconnected_at.isoformat(),
    }
