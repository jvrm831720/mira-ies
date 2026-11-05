"""Fail-closed boundary for the future Composio SDK adapter.

This foundation deliberately does not create sessions or execute tools. The SDK
adapter is added in a later integration wave after credentials and policy are set.
"""

from __future__ import annotations

from app.core.config import Settings, get_settings


class ComposioNotConfigured(RuntimeError):
    """Raised when a Composio operation is attempted before activation."""


def composio_is_configured(settings: Settings | None = None) -> bool:
    config = settings or get_settings()
    return bool(config.composio_enabled and config.composio_api_key)


def composio_toolkit_allowed(toolkit_slug: str, settings: Settings | None = None) -> bool:
    """Fail closed: only explicitly listed toolkit slugs are eligible."""
    config = settings or get_settings()
    slug = toolkit_slug.strip().lower()
    if not slug:
        return False
    allowed = {
        item.strip().lower()
        for item in config.composio_allowed_toolkits.split(",")
        if item.strip()
    }
    return slug in allowed


def require_composio_configuration(settings: Settings | None = None) -> Settings:
    config = settings or get_settings()
    if not composio_is_configured(config):
        raise ComposioNotConfigured(
            "Composio está desativado. Configure COMPOSIO_ENABLED e COMPOSIO_API_KEY."
        )
    return config
