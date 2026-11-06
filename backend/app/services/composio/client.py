"""Lazy Composio SDK adapter. All network access stays server-side."""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from app.services.composio.gateway import require_composio_configuration


class ComposioSDKUnavailable(RuntimeError):
    pass


@lru_cache(maxsize=1)
def _client_for_key(api_key: str) -> Any:
    try:
        from composio import Composio
    except ImportError as exc:
        raise ComposioSDKUnavailable("O SDK Composio não está instalado.") from exc
    return Composio(api_key=api_key)


def get_composio_client() -> Any:
    settings = require_composio_configuration()
    return _client_for_key(settings.composio_api_key or "")


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    for method_name in ("model_dump", "dict"):
        method = getattr(value, method_name, None)
        if callable(method):
            try:
                result = method()
                if isinstance(result, dict):
                    return result
            except Exception:
                pass
    raw = getattr(value, "__dict__", None)
    return raw if isinstance(raw, dict) else {}


def list_toolkits() -> list[dict[str, Any]]:
    """Fetch every page of the live toolkit catalog; never hard-code providers."""
    client = get_composio_client()
    cursor: str | None = None
    seen_cursors: set[str] = set()
    normalized: dict[str, dict[str, Any]] = {}

    while True:
        response = client.toolkits.list(
            limit=100,
            sort_by="alphabetically",
            managed_by="all",
            cursor=cursor,
        )
        response_data = _as_dict(response)
        if isinstance(response, dict):
            items = response.get("items") or response.get("data") or []
            next_cursor = response.get("next_cursor") or response.get("nextCursor")
        else:
            items = getattr(response, "items", []) or []
            next_cursor = (
                getattr(response, "next_cursor", None)
                or getattr(response, "nextCursor", None)
                or response_data.get("next_cursor")
                or response_data.get("nextCursor")
            )

        for item in items:
            data = _as_dict(item)
            slug = data.get("slug") or data.get("toolkit_slug") or getattr(item, "slug", None)
            if not isinstance(slug, str) or not slug.strip():
                continue
            normalized[slug.strip().lower()] = {
                "slug": slug.strip().lower(),
                "name": data.get("name") or data.get("display_name") or slug,
                "description": data.get("description"),
                "categories": data.get("categories") or [],
                "app_url": data.get("app_url") or data.get("website"),
                "logo": data.get("logo") or data.get("logo_url"),
            }

        if not next_cursor or next_cursor in seen_cursors:
            break
        seen_cursors.add(next_cursor)
        cursor = next_cursor

    return sorted(normalized.values(), key=lambda item: item["name"].lower())


def list_tools_for_toolkit(toolkit_slug: str) -> list[dict[str, Any]]:
    """Return live tool schemas for one toolkit, with a bounded catalog request."""
    client = get_composio_client()
    response = client.tools.get_raw_composio_tools(toolkits=[toolkit_slug.upper()], limit=1000)
    normalized: list[dict[str, Any]] = []
    for item in response or []:
        data = _as_dict(item)
        slug = data.get("slug") or data.get("tool_slug") or getattr(item, "slug", None)
        if not isinstance(slug, str) or not slug.strip():
            continue
        normalized.append({
            "slug": slug.strip().upper(),
            "name": data.get("name") or slug,
            "description": data.get("description"),
            "input_parameters": data.get("input_parameters") or data.get("inputParameters") or {},
        })
    return sorted(normalized, key=lambda item: item["slug"])


def validate_tool_slugs(toolkit_slug: str, tool_slugs: list[str]) -> list[str]:
    """Validate selected tools against the live schemas for the exact toolkit."""
    available = {item["slug"] for item in list_tools_for_toolkit(toolkit_slug)}
    validated = sorted({slug.strip().upper() for slug in tool_slugs if isinstance(slug, str)})
    if any(not slug or len(slug) > 120 for slug in validated):
        raise ValueError("Tool slug inválido.")
    unknown = sorted(set(validated) - available)
    if unknown:
        raise ValueError(f"Ferramentas não pertencem ao toolkit ou não existem: {', '.join(unknown)}")
    return validated


def create_connect_link(
    *,
    user_id: str,
    auth_config_id: str,
    callback_url: str | None = None,
    allow_multiple: bool = False,
) -> dict[str, Any]:
    """Create a Composio Connect Link (hosted OAuth). Returns redirect_url only."""
    client = get_composio_client()
    kwargs: dict[str, Any] = {}
    if callback_url:
        kwargs["callback_url"] = callback_url
    if allow_multiple:
        kwargs["allow_multiple"] = True
    request = client.connected_accounts.link(user_id, auth_config_id, **kwargs)
    data = _as_dict(request)
    redirect_url = (
        data.get("redirect_url")
        or getattr(request, "redirect_url", None)
        or data.get("redirectUrl")
    )
    if not isinstance(redirect_url, str) or not redirect_url.strip():
        raise RuntimeError("Composio não retornou redirect_url para o Connect Link.")
    return {
        "redirect_url": redirect_url.strip(),
        "connection_id": data.get("id") or getattr(request, "id", None),
        "connected_account_id": data.get("connected_account_id") or data.get("connectedAccountId"),
    }


def _normalize_account_row(item: Any) -> dict[str, Any] | None:
    row = _as_dict(item)
    account_id = (
        row.get("id")
        or row.get("nanoid")
        or row.get("connected_account_id")
        or getattr(item, "id", None)
    )
    if not isinstance(account_id, str) or not account_id.strip():
        return None
    toolkit = row.get("toolkit_slug") or row.get("toolkit")
    if isinstance(toolkit, dict):
        toolkit = toolkit.get("slug")
    if not toolkit:
        toolkit = row.get("appName") or row.get("app_name")
    status = row.get("status") or getattr(item, "status", None) or "active"
    user_id = row.get("user_id") or row.get("userId") or row.get("entity_id")
    return {
        "connected_account_id": account_id.strip(),
        "toolkit_slug": str(toolkit).strip().lower() if toolkit else "unknown",
        "auth_config_id": row.get("auth_config_id") or row.get("authConfigId"),
        "display_name": row.get("display_name") or row.get("alias") or row.get("name"),
        "status": str(status).strip().lower(),
        "user_id": str(user_id).strip() if user_id else None,
    }


def list_connected_accounts_for_user(user_id: str) -> list[dict[str, Any]]:
    """List remote connected accounts for one opaque Composio user id."""
    client = get_composio_client()
    response = client.connected_accounts.list(user_ids=[user_id], limit=100)
    data = _as_dict(response)
    if isinstance(response, dict):
        items = response.get("items") or response.get("data") or []
    else:
        items = getattr(response, "items", None) or data.get("items") or data.get("data") or []

    normalized: list[dict[str, Any]] = []
    for item in items or []:
        row = _normalize_account_row(item)
        if row:
            normalized.append(row)
    return normalized


def get_connected_account(connected_account_id: str) -> dict[str, Any] | None:
    """Fetch one connected account by id from Composio; None if missing."""
    client = get_composio_client()
    accounts = client.connected_accounts
    item = None
    if hasattr(accounts, "get"):
        try:
            item = accounts.get(connected_account_id)
        except Exception:
            item = None
    if item is None and hasattr(accounts, "retrieve"):
        try:
            item = accounts.retrieve(connected_account_id)
        except Exception:
            item = None
    if item is None:
        return None
    return _normalize_account_row(item)


def revoke_connected_account(connected_account_id: str) -> None:
    """Revoke/delete a connected account at Composio. Raises on failure."""
    client = get_composio_client()
    accounts = client.connected_accounts
    if hasattr(accounts, "revoke"):
        accounts.revoke(connected_account_id)
        return
    if hasattr(accounts, "delete"):
        accounts.delete(connected_account_id)
        return
    raise RuntimeError("SDK Composio não expõe revoke/delete de connected accounts.")


def list_onboarding_auth_configs() -> list[dict[str, str]]:
    """Only enabled auth configs; never expose OAuth credentials or secrets."""
    client = get_composio_client()
    cursor: str | None = None
    seen: set[str] = set()
    result: dict[tuple[str, str], dict[str, str]] = {}
    while True:
        kwargs: dict[str, Any] = {"limit": 200}
        if cursor:
            kwargs["cursor"] = cursor
        page = client.auth_configs.list(**kwargs)
        data = _as_dict(page)
        items = (page.get("items") or [] if isinstance(page, dict)
                 else getattr(page, "items", None) or data.get("items") or [])
        for item in items:
            row = _as_dict(item)
            toolkit = row.get("toolkit") or getattr(item, "toolkit", None)
            toolkit_data = _as_dict(toolkit)
            slug = (toolkit_data.get("slug") or row.get("toolkit_slug")
                    or (toolkit if isinstance(toolkit, str) else ""))
            config_id = row.get("id") or getattr(item, "id", None)
            status = str(row.get("status") or getattr(item, "status", "ENABLED")).upper().split(".")[-1]
            if not isinstance(slug, str) or not isinstance(config_id, str) or status not in {"ENABLED", "ACTIVE"}:
                continue
            result[(slug.lower(), config_id)] = {
                "toolkit_slug": slug.lower(),
                "auth_config_id": config_id,
                "auth_scheme": str(row.get("auth_scheme") or getattr(item, "auth_scheme", "OAUTH2")).upper().split(".")[-1],
            }
        nxt = data.get("next_cursor") or getattr(page, "next_cursor", None)
        if not isinstance(nxt, str) or not nxt or nxt in seen:
            break
        seen.add(nxt)
        cursor = nxt
    return list(result.values())
