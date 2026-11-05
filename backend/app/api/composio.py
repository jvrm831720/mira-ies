"""Tenant-scoped Composio catalog and Connect Link endpoints.

Tool execution is intentionally not exposed in this foundation phase.
"""
from __future__ import annotations

import json
import re

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.auth import AuthContext, require_min_role
from app.core.config import get_settings
from app.services.composio.client import ComposioAPIError, ComposioClient, ComposioNotConfigured

router = APIRouter(prefix="/composio", tags=["Composio — ferramentas organizacionais"])
_TOOLKIT_SLUG = re.compile(r"^[a-z][a-z0-9_-]{1,79}$")


def _client() -> ComposioClient:
    settings = get_settings()
    if not settings.composio_enabled:
        raise HTTPException(status_code=503, detail="Integração Composio desabilitada.")
    try:
        return ComposioClient(
            api_key=settings.composio_api_key or "",
            base_url=settings.composio_base_url,
            timeout=settings.composio_timeout_seconds,
        )
    except ComposioNotConfigured as exc:
        raise HTTPException(status_code=503, detail="Composio não configurado no servidor.") from exc


def _auth_configs() -> dict[str, str]:
    raw = get_settings().composio_auth_configs_json
    try:
        value = json.loads(raw or "{}")
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail="Mapa de auth configs do Composio inválido.") from exc
    if not isinstance(value, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in value.items()):
        raise HTTPException(status_code=503, detail="Mapa de auth configs do Composio inválido.")
    return value


class ConnectLinkRequest(BaseModel):
    toolkit_slug: str = Field(min_length=2, max_length=80, pattern=r"^[a-z][a-z0-9_-]+$")


@router.get("/status")
async def composio_status(auth: AuthContext = Depends(require_min_role("admin"))):
    settings = get_settings()
    configured = bool(settings.composio_enabled and settings.composio_api_key)
    return {
        "enabled": settings.composio_enabled,
        "configured": configured,
        "auth_configured_toolkits": sorted(_auth_configs().keys()),
        "execution_enabled": False,
    }


@router.get("/tools")
async def list_composio_tools(
    toolkit_slug: str | None = Query(default=None, min_length=2, max_length=80),
    search: str | None = Query(default=None, min_length=2, max_length=120),
    _auth: AuthContext = Depends(require_min_role("admin")),
):
    if toolkit_slug and not _TOOLKIT_SLUG.fullmatch(toolkit_slug):
        raise HTTPException(status_code=422, detail="Toolkit inválido.")
    try:
        return await _client().list_tools(toolkit_slug=toolkit_slug, search=search)
    except ComposioNotConfigured as exc:
        raise HTTPException(status_code=503, detail="Composio não configurado.") from exc
    except ComposioAPIError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/connections/link", status_code=201)
async def create_connection_link(
    body: ConnectLinkRequest,
    auth: AuthContext = Depends(require_min_role("admin")),
):
    """Start a provider authorization for this institution, never for a caller-supplied user."""
    auth_config_id = _auth_configs().get(body.toolkit_slug)
    if not auth_config_id:
        raise HTTPException(status_code=409, detail="Toolkit sem auth config configurada no servidor.")
    # The organization is the Composio principal: members of one tenant share
    # the institution's connected account, while different tenants stay isolated.
    composio_user_id = f"mira_tenant_{auth.tenant_id}"
    alias = f"mira-{auth.tenant_id}-{body.toolkit_slug}"
    try:
        result = await _client().create_auth_link(
            auth_config_id=auth_config_id,
            user_id=composio_user_id,
            alias=alias,
        )
    except ComposioNotConfigured as exc:
        raise HTTPException(status_code=503, detail="Composio não configurado.") from exc
    except ComposioAPIError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    redirect_url = result.get("redirect_url")
    if not isinstance(redirect_url, str) or not redirect_url.startswith("https://"):
        raise HTTPException(status_code=502, detail="Composio não retornou um link HTTPS válido.")
    return {
        "toolkit_slug": body.toolkit_slug,
        "redirect_url": redirect_url,
        "expires_at": result.get("expires_at"),
        "status": "pending_authorization",
    }
