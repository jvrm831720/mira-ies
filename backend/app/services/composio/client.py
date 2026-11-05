"""Lazy Composio SDK adapter. All network access stays server-side."""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from app.core.config import get_settings
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
    """Fetch the live catalog. Never returns a hard-coded provider allowlist."""
    client = get_composio_client()
    response = client.toolkits.get()
    if isinstance(response, dict):
        items = response.get("items") or response.get("toolkits") or response.get("data") or []
    else:
        items = response if isinstance(response, (list, tuple)) else getattr(response, "items", [])
    normalized: list[dict[str, Any]] = []
    for item in items or []:
        data = _as_dict(item)
        slug = data.get("slug") or data.get("toolkit_slug") or getattr(item, "slug", None)
        if not isinstance(slug, str) or not slug.strip():
            continue
        normalized.append({
            "slug": slug.strip().lower(),
            "name": data.get("name") or data.get("display_name") or slug,
            "description": data.get("description"),
            "categories": data.get("categories") or [],
            "app_url": data.get("app_url") or data.get("website"),
            "logo": data.get("logo") or data.get("logo_url"),
        })
    return sorted(normalized, key=lambda item: item["name"].lower())


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
