"""Autenticacao tenant-scoped por sessao Mira ou API key legada."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.mira_security import decode_access_token
from app.core.security import hash_api_key
from app.db.session import get_db
from app.models.auth import TenantRole, User, UserSession
from app.models.tenant import Tenant

# Hierarquia simples: admin > coordinator > operator > viewer
ROLE_RANK = {"viewer": 1, "operator": 2, "coordinator": 3, "admin": 4}


@dataclass
class AuthContext:
    tenant: Tenant
    tenant_id: str
    tenant_slug: str
    user_id: Optional[str] = None
    role: Optional[str] = None  # None = API key de integração
    session_id: Optional[str] = None
    aal: int = 1
    authenticated_at: Optional[int] = None
    permissions: Optional[frozenset[str]] = None
    custom_role_id: Optional[str] = None


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
    await _set_tenant_rls_context(db, user.tenant_id)
    session_id = claims.get("sid")
    if not session_id:
        raise _unauthorized("Sessão antiga ou inválida. Entre novamente.")
    session = await db.get(UserSession, session_id)
    now = int(__import__("time").time())
    if (
        not session
        or session.user_id != user.id
        or session.tenant_id != user.tenant_id
        or session.revoked_at is not None
        or session.expires_at.timestamp() <= now
        or session.aal != int(claims.get("aal", 1))
    ):
        raise _unauthorized("Esta sessão foi encerrada ou expirou.")
    # MFA é obrigatório para todas as contas humanas em todos os tenants.
    # Revogue tokens antigos ou sessões emitidas sem nível AAL2.
    if not user.mfa_enabled_at or int(claims.get("aal", 1)) < 2:
        session.revoked_at = datetime.now(timezone.utc)
        session.revoked_by_user_id = user.id
        session.revoke_reason = "global_mfa_required"
        await db.commit()
        raise _unauthorized(
            "TOTP obrigatório para todas as contas. Entre novamente e configure seu autenticador."
        )
    tenant = await db.get(Tenant, user.tenant_id)
    if not tenant or not tenant.is_active:
        raise _unauthorized()
    role = user.role if getattr(user, "role", None) in ROLE_RANK else "coordinator"
    custom_permissions = None
    custom_role_id = getattr(user, "custom_role_id", None)
    if custom_role_id:
        custom_role_result = await db.execute(
            select(TenantRole).where(
                TenantRole.id == custom_role_id,
                TenantRole.tenant_id == tenant.id,
                TenantRole.is_active.is_(True),
            )
        )
        custom_role = custom_role_result.scalar_one_or_none()
        if custom_role:
            role = custom_role.base_role if custom_role.base_role in ROLE_RANK and custom_role.base_role != "admin" else "viewer"
            base_rank = ROLE_RANK.get(role, 0)
            permission_ceiling = {
                "access.viewer": 1, "dashboard.view": 1, "students.view": 1,
                "access.operator": 2, "students.create": 2, "students.edit": 2,
                "campaigns.view": 2, "campaigns.create": 2, "campaigns.edit": 2,
                "members.view": 2, "data.view": 2,
                "access.coordinator": 3, "data.import": 3, "audit.view": 3,
                "students.sensitive.view": 3, "campaigns.approve": 3,
                "campaigns.execute": 3,
                "members.manage": 4, "permissions.manage": 4, "settings.manage": 4,
                "students.delete": 4, "campaigns.delete": 4, "critical.manage": 4,
            }
            custom_permissions = frozenset(
                item for item in (custom_role.permissions or [])
                if isinstance(item, str)
                and permission_ceiling.get(item, 99) <= base_rank
            )
        else:
            role = "viewer"
            custom_permissions = frozenset()
    await _set_tenant_rls_context(db, tenant.id)
    return AuthContext(
        tenant=tenant,
        tenant_id=tenant.id,
        tenant_slug=tenant.slug,
        user_id=user.id,
        role=role,
        session_id=session.id,
        aal=int(claims.get("aal", 1)),
        authenticated_at=int(claims.get("iat", 0)),
        permissions=custom_permissions,
        custom_role_id=custom_role_id,
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


def _permission_for_request(request: Request, fallback_role: str) -> str:
    path = request.url.path.removeprefix("/api/v1")
    method = request.method.upper()
    if path.startswith("/students"):
        if method in {"GET", "HEAD"}:
            return "students.view"
        if method in {"PATCH", "PUT"}:
            return "students.edit"
        if method == "DELETE":
            return "students.delete"
    if path.startswith("/upload") or path.startswith("/connectors") and method in {"POST", "PUT", "PATCH"}:
        return "data.import"
    if path.startswith("/connectors"):
        return "data.view"
    if path.startswith("/agents/retention/campaigns"):
        if path.endswith("/approve"):
            return "campaigns.approve"
        if path.endswith("/execute") or path.endswith("/schedule"):
            return "campaigns.execute"
        if method == "GET":
            return "campaigns.view"
        if method == "POST":
            return "campaigns.create"
        if method in {"PATCH", "PUT"}:
            return "campaigns.edit"
        if method == "DELETE":
            return "campaigns.delete"
    if path.startswith("/org/members"):
        return "members.view" if method == "GET" else "members.manage"
    if path.startswith("/org/invites"):
        return "members.view" if method == "GET" else "members.manage"
    return f"access.{fallback_role}"


def require_min_role(min_role: str):
    """Exige rank >= min_role (admin passa em tudo)."""
    threshold = ROLE_RANK.get(min_role, 99)

    async def _dep(request: Request, auth: AuthContext = Depends(get_current_tenant)) -> AuthContext:
        if auth.permissions is not None:
            required_permission = _permission_for_request(request, min_role)
            allowed = required_permission in auth.permissions
            if not allowed:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Você não tem permissão para esta ação.")
            return auth
        rank = ROLE_RANK.get(auth.role or "viewer", 0)
        if rank < threshold:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Você não tem permissão para esta ação.",
            )
        return auth

    return _dep


def require_permission(permission: str):
    """Exige uma permissão explícita; sessões legadas usam a matriz padrão por papel."""
    async def _dep(auth: AuthContext = Depends(get_current_tenant)) -> AuthContext:
        if auth.permissions is not None:
            allowed = permission in auth.permissions
        else:
            role = auth.role or "viewer"
            rank = ROLE_RANK.get(role, 0)
            defaults = {
                "dashboard.view": 1, "students.view": 1, "members.view": 2,
                "students.create": 2, "students.edit": 2, "data.import": 3,
                "campaigns.view": 2, "campaigns.create": 2, "campaigns.edit": 2,
                "campaigns.approve": 3, "campaigns.execute": 3,
                "members.manage": 4, "permissions.manage": 4, "settings.manage": 4,
                "students.delete": 4, "campaigns.delete": 4, "critical.manage": 4,
                "audit.view": 3, "data.view": 2, "students.sensitive.view": 3,
            }
            allowed = rank >= defaults.get(permission, 99)
        if not allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Você não tem permissão para esta ação.")
        return auth
    return _dep
