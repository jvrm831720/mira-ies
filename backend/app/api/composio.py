"""Tenant-scoped Composio catalog and exposure policy endpoints."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthContext, require_min_role
from app.db.session import get_db
from app.models.composio_connection import TenantComposioToolkitPolicy
from app.services.composio.client import (
    ComposioSDKUnavailable,
    list_toolkits,
    validate_tool_slugs,
)
from app.services.composio.gateway import ComposioNotConfigured, require_composio_configuration

router = APIRouter(prefix="/integrations/composio", tags=["Composio"])


class ToolkitPolicyPayload(BaseModel):
    enabled: bool
    tool_slugs: list[str] = Field(default_factory=list, max_length=500)


def _catalog_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ComposioNotConfigured):
        return HTTPException(status_code=503, detail="Integração Composio desativada ou sem configuração.")
    if isinstance(exc, ComposioSDKUnavailable):
        return HTTPException(status_code=503, detail="SDK Composio indisponível no backend.")
    return HTTPException(status_code=502, detail="Não foi possível consultar o catálogo Composio.")


@router.get("/catalog")
async def get_catalog(
    auth: AuthContext = Depends(require_min_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    try:
        require_composio_configuration()
        catalog = list_toolkits()
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
    auth: AuthContext = Depends(require_min_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    slug = toolkit_slug.strip().lower()
    if not slug or len(slug) > 80 or not slug.replace("_", "").replace("-", "").isalnum():
        raise HTTPException(status_code=422, detail="Toolkit slug inválido.")

    try:
        require_composio_configuration()
        known_toolkits = {item["slug"] for item in list_toolkits()}
        if slug not in known_toolkits:
            raise HTTPException(status_code=404, detail="Toolkit não encontrado no catálogo Composio.")
        tools = validate_tool_slugs(body.tool_slugs) if body.tool_slugs else []
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
