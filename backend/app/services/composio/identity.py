"""Stable, opaque Composio identities derived from MIRA tenant identity."""

from __future__ import annotations

import hashlib
import hmac

from app.core.config import get_settings


def composio_user_id_for_tenant(tenant_id: str) -> str:
    """Return a deterministic, non-PII Composio user ID for one MIRA tenant.

    Do not use email, tenant slug, display name, or a client-provided user ID.
    Member-owned connections can be introduced later with a separate namespace.
    """
    normalized = str(tenant_id).strip().lower()
    if not normalized:
        raise ValueError("tenant_id é obrigatório")
    configured_secret = get_settings().composio_identity_secret
    if not configured_secret:
        raise RuntimeError("COMPOSIO_IDENTITY_SECRET é obrigatório para derivar identidades estáveis.")
    secret = configured_secret.encode("utf-8")
    digest = hmac.new(secret, normalized.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"mira_tenant_{digest[:40]}"
