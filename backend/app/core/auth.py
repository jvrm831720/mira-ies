"""Autenticacao tenant-scoped por sessao Mira ou API key legada."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.mira_security import decode_access_token
from app.core.security import hash_api_key
from app.db.session import get_db
from app.models.auth import User
from app.models.tenant import Tenant


@dataclass
class AuthContext:
    tenant: Tenant
    tenant_id: str
    tenant_slug: str
    user_id: Optional[str] = None


def _unauthorized(detail: str = "API key ou sessão inválida.") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def _auth_session_token(token: str, db: AsyncSession) -> AuthContext:
    claims = decode_access_token(token)
    if not claims:
        raise _unauthorized()
    result = await db.execute(
        select(User).where(User.id == claims.get("sub"), User.tenant_id == claims.get("tid"))
    )
    user = result.scalar_one_or_none()
    if not user or not user.is_active or user.auth_version != int(claims.get("ver", -1)):
        raise _unauthorized()
    tenant = await db.get(Tenant, user.tenant_id)
    if not tenant or not tenant.is_active:
        raise _unauthorized()
    return AuthContext(tenant=tenant, tenant_id=tenant.id, tenant_slug=tenant.slug, user_id=user.id)


async def get_current_tenant(
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> AuthContext:
    settings = get_settings()
    raw_key = x_api_key
    session_token: Optional[str] = None

    if not raw_key and authorization:
        parts = authorization.split(" ", 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            credential = parts[1].strip()
            if credential.count(".") == 2:
                session_token = credential
            else:
                raw_key = credential
        elif len(parts) == 1:
            raw_key = parts[0].strip()

    if session_token:
        return await _auth_session_token(session_token, db)

    if not raw_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key ou sessão ausente. Envie X-API-Key ou Authorization: Bearer.",
            headers={"WWW-Authenticate": "Bearer"},
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
        raise _unauthorized("API key inválida ou tenant inativo.")
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
