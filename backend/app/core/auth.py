"""Autenticacao tenant-scoped por sessao Mira ou API key legada."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.mira_security import decode_access_token
from app.core.security import hash_api_key
from app.db.session import get_db
from app.models.auth import User
from app.models.tenant import Tenant

# Hierarquia simples: admin > coordinator > operator > viewer
ROLE_RANK = {"viewer": 1, "operator": 2, "coordinator": 3, "admin": 4}


@dataclass
class AuthContext:
    tenant: Tenant
    tenant_id: str
    tenant_slug: str
    user_id: Optional[str] = None
    role: Optional[str] = None  # None = API key legada (poder equivalente a admin em dev)


async def _set_tenant_rls_context(db: AsyncSession, tenant_id: str) -> None:
    """Set transaction-local tenant context for tables protected by PostgreSQL RLS."""
    await db.execute(text("SELECT set_config('app.tenant_id', :tenant_id, true)"), {"tenant_id": tenant_id})


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
    if claims.get("purpose", "session") != "session":
        raise _unauthorized()
    if user.mfa_enabled_at and int(claims.get("aal", 1)) < 2:
        raise _unauthorized("Autenticação multifator necessária.")
    tenant = await db.get(Tenant, user.tenant_id)
    if not tenant or not tenant.is_active:
        raise _unauthorized()
    role = user.role if getattr(user, "role", None) in ROLE_RANK else "coordinator"
    await _set_tenant_rls_context(db, tenant.id)
    return AuthContext(
        tenant=tenant,
        tenant_id=tenant.id,
        tenant_slug=tenant.slug,
        user_id=user.id,
        role=role,
    )


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
        await _set_tenant_rls_context(db, tenant.id)
        return AuthContext(
            tenant=tenant, tenant_id=tenant.id, tenant_slug=tenant.slug, role="admin"
        )

    key_hash = hash_api_key(raw_key)
    result = await db.execute(
        select(Tenant).where(Tenant.api_key_hash == key_hash, Tenant.is_active == True)  # noqa: E712
    )
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise _unauthorized("API key inválida ou tenant inativo.")
    # API key de integração: privilégio operacional alto (sem user)
    await _set_tenant_rls_context(db, tenant.id)
    return AuthContext(
        tenant=tenant, tenant_id=tenant.id, tenant_slug=tenant.slug, role="admin"
    )


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


def require_roles(*allowed: str):
    """Dependency factory: exige um dos papéis (ou rank superior)."""
    min_rank = min(ROLE_RANK.get(r, 99) for r in allowed) if allowed else 0

    async def _dep(auth: AuthContext = Depends(get_current_tenant)) -> AuthContext:
        role = auth.role or "viewer"
        rank = ROLE_RANK.get(role, 0)
        if rank < min_rank and role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Você não tem permissão para esta ação.",
            )
        # Also accept if role is in allowed list even with weird ranks
        if allowed and role not in allowed and rank < min_rank:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Você não tem permissão para esta ação.",
            )
        if allowed and role not in allowed:
            # rank-based: admin can do coordinator things
            highest_allowed = max(ROLE_RANK.get(r, 0) for r in allowed)
            if rank < highest_allowed and role not in allowed:
                # allow higher rank than minimum required among allowed
                if rank >= min_rank:
                    return auth
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Você não tem permissão para esta ação.",
                )
        return auth

    return _dep


def require_min_role(min_role: str):
    """Exige rank >= min_role (admin passa em tudo)."""
    threshold = ROLE_RANK.get(min_role, 99)

    async def _dep(auth: AuthContext = Depends(get_current_tenant)) -> AuthContext:
        rank = ROLE_RANK.get(auth.role or "viewer", 0)
        if rank < threshold:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Você não tem permissão para esta ação.",
            )
        return auth

    return _dep
