"""Tenant-scoped Composio catalog, policy and connection endpoints."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.auth import AuthContext, require_permission
from app.db.session import get_db
from app.models.composio_connection import TenantComposioToolkitPolicy
from app.services.composio.client import (
    ComposioSDKUnavailable,
    list_toolkits,
    list_tools_for_toolkit,
    validate_tool_slugs,
)
from app.services.composio.connections import (
    ConnectionDenied,
    complete_connect_callback,
    list_tenant_accounts,
    revoke_tenant_account,
    start_connect_link,
)
from app.services.composio.gateway import ComposioNotConfigured, require_composio_configuration
from app.services.composio.sessions import ensure_tenant_session

router = APIRouter(prefix="/integrations/composio", tags=["Composio"])


class ToolkitPolicyPayload(BaseModel):
    enabled: bool
    tool_slugs: list[str] = Field(default_factory=list, max_length=500)


class StartConnectPayload(BaseModel):
    toolkit_slug: str = Field(min_length=1, max_length=80)
    auth_config_id: str = Field(min_length=1, max_length=80)
    callback_url: str | None = Field(default=None, max_length=500)


class CompleteConnectPayload(BaseModel):
    state: str = Field(min_length=8, max_length=128)
    connected_account_id: str | None = Field(default=None, max_length=120)


def _catalog_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ComposioNotConfigured):
        return HTTPException(status_code=503, detail="Integração Composio desativada ou sem configuração.")
    if isinstance(exc, ComposioSDKUnavailable):
        return HTTPException(status_code=503, detail="SDK Composio indisponível no backend.")
    if isinstance(exc, ConnectionDenied):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=502, detail="Falha na operação Composio.")


@router.get("/catalog")
async def get_catalog(
    auth: AuthContext = Depends(require_permission("settings.manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        require_composio_configuration()
        catalog = await run_in_threadpool(list_toolkits)
    except Exception as exc:
        raise _catalog_error(exc) from exc

    rows = await db.execute(
        select(TenantComposioToolkitPolicy).where(
            TenantComposioToolkitPolicy.tenant_id == auth.tenant_id
        )
    )
    policies = {row.toolkit_slug: row for row in rows.scalars().all()}
    return {
        "source": "composio_live_catalog",
        "items": [{
            **item,
            "enabled": bool(policies.get(item["slug"]) and policies[item["slug"]].is_enabled),
            "selected_tool_slugs": (
                policies[item["slug"]].tool_slugs
                if item["slug"] in policies else []
            ),
        } for item in catalog],
        "total": len(catalog),
    }


@router.put("/catalog/{toolkit_slug}/policy")
async def update_toolkit_policy(
    toolkit_slug: str,
    body: ToolkitPolicyPayload,
    auth: AuthContext = Depends(require_permission("settings.manage")),
    db: AsyncSession = Depends(get_db),
):
    slug = toolkit_slug.strip().lower()
    if not slug or len(slug) > 80 or not slug.replace("_", "").replace("-", "").isalnum():
        raise HTTPException(status_code=422, detail="Toolkit slug inválido.")

    try:
        require_composio_configuration()
        known_toolkits = {item["slug"] for item in await run_in_threadpool(list_toolkits)}
        if slug not in known_toolkits:
            raise HTTPException(status_code=404, detail="Toolkit não encontrado no catálogo Composio.")
        tools = await run_in_threadpool(validate_tool_slugs, slug, body.tool_slugs) if body.tool_slugs else []
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise _catalog_error(exc) from exc

    if body.enabled and not tools:
        raise HTTPException(
            status_code=422,
            detail="Selecione ao menos uma ferramenta antes de habilitar o toolkit.",
        )

    result = await db.execute(select(TenantComposioToolkitPolicy).where(
        TenantComposioToolkitPolicy.tenant_id == auth.tenant_id,
        TenantComposioToolkitPolicy.toolkit_slug == slug,
    ))
    row = result.scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if row is None:
        row = TenantComposioToolkitPolicy(
            tenant_id=auth.tenant_id,
            toolkit_slug=slug,
            is_enabled=body.enabled,
            tool_slugs=tools,
            updated_by_user_id=auth.user_id,
            updated_at=now,
        )
        db.add(row)
    else:
        row.is_enabled = body.enabled
        row.tool_slugs = tools
        row.updated_by_user_id = auth.user_id
        row.updated_at = now
    await db.commit()
    return {
        "toolkit_slug": row.toolkit_slug,
        "enabled": row.is_enabled,
        "tool_slugs": row.tool_slugs,
        "updated_at": row.updated_at.isoformat(),
    }


@router.get("/catalog/{toolkit_slug}/tools")
async def get_toolkit_tools(
    toolkit_slug: str,
    auth: AuthContext = Depends(require_permission("settings.manage")),
):
    slug = toolkit_slug.strip().lower()
    if not slug or len(slug) > 80 or not slug.replace("_", "").replace("-", "").isalnum():
        raise HTTPException(status_code=422, detail="Toolkit slug inválido.")
    try:
        require_composio_configuration()
        known_toolkits = {item["slug"] for item in await run_in_threadpool(list_toolkits)}
        if slug not in known_toolkits:
            raise HTTPException(status_code=404, detail="Toolkit não encontrado no catálogo Composio.")
        tools = await run_in_threadpool(list_tools_for_toolkit, slug)
    except HTTPException:
        raise
    except Exception as exc:
        raise _catalog_error(exc) from exc
    return {"toolkit_slug": slug, "items": tools, "total": len(tools)}


@router.post("/session")
async def provision_session(
    auth: AuthContext = Depends(require_permission("settings.manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        require_composio_configuration()
        row = await ensure_tenant_session(
            db, tenant_id=auth.tenant_id, actor_user_id=auth.user_id
        )
        await db.commit()
    except Exception as exc:
        raise _catalog_error(exc) from exc
    return {
        "tenant_id": row.tenant_id,
        "composio_user_id": row.composio_user_id,
        "status": row.status,
        "session_id": row.session_id,
    }


@router.post("/connections/start")
async def start_connection(
    body: StartConnectPayload,
    auth: AuthContext = Depends(require_permission("settings.manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await start_connect_link(
            db,
            tenant_id=auth.tenant_id,
            actor_user_id=auth.user_id,
            toolkit_slug=body.toolkit_slug,
            auth_config_id=body.auth_config_id,
            callback_url=body.callback_url,
        )
    except Exception as exc:
        raise _catalog_error(exc) from exc
    return result


@router.post("/connections/complete")
async def complete_connection(
    body: CompleteConnectPayload,
    auth: AuthContext = Depends(require_permission("settings.manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await complete_connect_callback(
            db,
            tenant_id=auth.tenant_id,
            state_token=body.state,
            connected_account_id=body.connected_account_id,
        )
    except Exception as exc:
        raise _catalog_error(exc) from exc
    return result


@router.get("/connections")
async def list_connections(
    sync: bool = Query(default=False),
    auth: AuthContext = Depends(require_permission("settings.manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        items = await list_tenant_accounts(
            db, tenant_id=auth.tenant_id, sync_remote=sync
        )
    except Exception as exc:
        raise _catalog_error(exc) from exc
    return {"items": items, "total": len(items)}


@router.delete("/connections/{connected_account_id}")
async def delete_connection(
    connected_account_id: str,
    auth: AuthContext = Depends(require_permission("settings.manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await revoke_tenant_account(
            db,
            tenant_id=auth.tenant_id,
            connected_account_id=connected_account_id,
            revoke_remote=True,
        )
    except Exception as exc:
        raise _catalog_error(exc) from exc
    return result
