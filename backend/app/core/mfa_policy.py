"""Resolução das políticas institucionais de MFA."""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth import MfaTenantPolicy, User

VALID_MFA_ROLES = {"admin", "coordinator", "operator", "viewer"}


async def user_requires_mfa(db: AsyncSession, user: User) -> bool:
    await db.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": user.tenant_id},
    )
    if user.mfa_enabled_at is not None:
        return True
    policy = await db.get(MfaTenantPolicy, user.tenant_id)
    if not policy:
        return False
    return bool(policy.require_mfa_all or user.role in (policy.required_roles or []))


async def get_tenant_mfa_policy(db: AsyncSession, tenant_id: str) -> dict:
    await db.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": tenant_id},
    )
    policy = await db.get(MfaTenantPolicy, tenant_id)
    return {
        "require_mfa_all": bool(policy.require_mfa_all) if policy else False,
        "required_roles": list(policy.required_roles or []) if policy else [],
        "updated_at": policy.updated_at.isoformat() if policy and policy.updated_at else None,
    }
