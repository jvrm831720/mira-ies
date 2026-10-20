"""Autenticacao por API Key (X-API-Key). Resolve Tenant a partir da chave."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import hash_api_key
from app.db.session import get_db
from app.models.tenant import Tenant


@dataclass
class AuthContext:
    tenant: Tenant
    tenant_id: str
    tenant_slug: str


async def get_current_tenant(
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> AuthContext:
    settings = get_settings()
    raw_key = x_api_key
    if not raw_key and authorization:
        parts = authorization.split(" ", 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            raw_key = parts[1].strip()
        elif len(parts) == 1:
            raw_key = parts[0].strip()

    if not raw_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key ausente. Envie o header X-API-Key.",
            headers={"WWW-Authenticate": "API-Key"},
        )

    if settings.app_env == "development" and settings.dev_api_key and raw_key == settings.dev_api_key:
        tenant = await _get_or_bootstrap_default(db, raw_key)
        return AuthContext(tenant=tenant, tenant_id=tenant.id, tenant_slug=tenant.slug)

    key_hash = hash_api_key(raw_key)
    result = await db.execute(
        select(Tenant).where(Tenant.api_key_hash == key_hash, Tenant.is_active == True)  # noqa: E712
    )
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key invalida ou tenant inativo.",
            headers={"WWW-Authenticate": "API-Key"},
        )
    return AuthContext(tenant=tenant, tenant_id=tenant.id, tenant_slug=tenant.slug)


async def _get_or_bootstrap_default(db: AsyncSession, raw_key: str) -> Tenant:
    result = await db.execute(select(Tenant).where(Tenant.slug == "default"))
    tenant = result.scalar_one_or_none()
    if tenant:
        if not tenant.api_key_hash:
            tenant.api_key_hash = hash_api_key(raw_key)
            await db.commit()
            await db.refresh(tenant)
        return tenant
    tenant = Tenant(
        slug="default", name="IES Demo", is_active=True,
        api_key_hash=hash_api_key(raw_key),
    )
    db.add(tenant)
    await db.commit()
    await db.refresh(tenant)
    return tenant


async def require_tenant_match(auth: AuthContext, claimed_slug: Optional[str]) -> None:
    if claimed_slug and claimed_slug != auth.tenant_slug:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"tenant_slug '{claimed_slug}' nao corresponde a API key (tenant '{auth.tenant_slug}').",
        )
