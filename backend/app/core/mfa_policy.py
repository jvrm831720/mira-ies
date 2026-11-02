"""Política global de MFA: TOTP obrigatório para todas as contas humanas."""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth import MfaTenantPolicy, User

VALID_MFA_ROLES = {"admin", "coordinator", "operator", "viewer"}


async def user_requires_mfa(_db: AsyncSession, _user: User) -> bool:
    """Nenhuma conta humana pode criar uma sessão sem concluir TOTP."""
    return True


async def get_tenant_mfa_policy(db: AsyncSession, tenant_id: str) -> dict:
    """Expõe a política global como somente leitura no contexto de cada tenant."""
    await db.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": tenant_id},
    )
    stored_policy = await db.get(MfaTenantPolicy, tenant_id)
    return {
        "require_mfa_all": True,
        "required_roles": [],
        "updated_at": (
            stored_policy.updated_at.isoformat()
            if stored_policy and stored_policy.updated_at
            else None
        ),
        "enforcement_scope": "global",
        "mutable": False,
    }
