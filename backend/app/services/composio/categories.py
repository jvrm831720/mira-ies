"""Curated MIRA taxonomy for communication integrations.

Composio toolkits are catalogued separately from native MIRA channel providers.
A toolkit being listed here never enables it or grants an agent permission to use it.
"""
from __future__ import annotations

from typing import Any

from app.core.config import Settings, get_settings


COMMUNICATION_TOOLKITS: dict[str, dict[str, str]] = {
    "gmail": {"name": "Gmail", "kind": "email"},
    "outlook": {"name": "Outlook", "kind": "email"},
    "slack": {"name": "Slack", "kind": "team_messaging"},
    "microsoft_teams": {"name": "Microsoft Teams", "kind": "team_messaging"},
    "zoom": {"name": "Zoom", "kind": "meetings"},
    "zoom_chat": {"name": "Zoom Team Chat", "kind": "team_messaging"},
    "aircall": {"name": "Aircall", "kind": "telephony"},
}


def annotate_communication_toolkit(item: dict[str, Any]) -> dict[str, Any]:
    """Attach MIRA's category metadata without changing the live Composio record."""
    slug = str(item.get("slug") or "").strip().lower()
    metadata = COMMUNICATION_TOOLKITS.get(slug)
    if not metadata:
        return {**item, "mira_category": None, "mira_category_label": None}
    return {
        **item,
        "mira_category": "communication",
        "mira_category_label": "Comunicação",
        "mira_channel": metadata["kind"],
    }


def native_communication_channels(settings: Settings | None = None) -> list[dict[str, Any]]:
    """Describe existing native MIRA channels without exposing provider secrets."""
    config = settings or get_settings()
    return [
        {
            "slug": "whatsapp",
            "name": "WhatsApp",
            "kind": "messaging",
            "integration_type": "native",
            "providers": [
                {
                    "slug": "waha",
                    "configured": bool(config.waha_api_url and config.waha_api_key),
                },
                {
                    "slug": "evolution",
                    "configured": bool(config.evolution_api_url and config.evolution_api_key),
                },
            ],
        },
        {
            "slug": "email_delivery",
            "name": "E-mail transacional",
            "kind": "email_delivery",
            "integration_type": "native",
            "providers": [
                {
                    "slug": "resend",
                    "configured": bool(config.resend_api_key and config.email_from),
                },
            ],
        },
        {
            "slug": "sms",
            "name": "SMS",
            "kind": "sms",
            "integration_type": "native",
            "providers": [
                {
                    "slug": "twilio",
                    "configured": bool(
                        config.twilio_account_sid
                        and config.twilio_auth_token
                        and config.twilio_from
                    ),
                },
            ],
        },
    ]


def communication_category(settings: Settings | None = None) -> dict[str, Any]:
    """Return the communication category split into Composio and native channels."""
    return {
        "slug": "communication",
        "name": "Comunicação",
        "description": (
            "E-mail, mensageria, colaboração, reuniões e telefonia "
            "para relacionamento com alunos, responsáveis, clientes e equipes."
        ),
        "composio_toolkits": [
            {"slug": slug, **metadata}
            for slug, metadata in COMMUNICATION_TOOLKITS.items()
        ],
        "native_channels": native_communication_channels(settings),
    }
