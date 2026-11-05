"""RBAC institucional: cargos personalizados, atribuições e auditoria."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthContext, get_current_tenant
from app.db.session import get_db
from app.models.auth import TenantRole, TenantRoleAudit, User
from app.services.membership import ensure_membership, sync_membership_role

router = APIRouter(prefix="/org", tags=["RBAC institucional"])

# Chaves estáveis: a API nunca aceita nomes de tela, SQL ou expressões fornecidas pelo cliente.
PERMISSION_CATALOG = {
    "access.viewer": "Acessar áreas de consulta",
    "access.operator": "Acessar operação",
    "access.coordinator": "Acessar coordenação",
    "dashboard.view": "Visualizar painel",
    "students.view": "Visualizar alunos",
    "students.sensitive.view": "Visualizar dados sensíveis de alunos",
    "students.create": "Criar registros de alunos",
    "students.edit": "Editar registros de alunos",
    "students.delete": "Excluir registros de alunos",
    "campaigns.view": "Visualizar campanhas",
    "campaigns.create": "Criar campanhas",
    "campaigns.edit": "Editar campanhas",
    "campaigns.approve": "Aprovar campanhas",
    "campaigns.execute": "Executar campanhas",
    "campaigns.delete": "Excluir campanhas",
    "members.view": "Visualizar membros",
    "members.manage": "Administrar membros",
    "permissions.manage": "Administrar cargos e permissões",
    "settings.manage": "Administrar configurações",
    "data.view": "Visualizar dados e integrações",
    "data.import": "Importar dados",
    "audit.view": "Consultar auditoria",
    "critical.manage": "Executar operações críticas",
}
BASE_ROLE_RANK = {"viewer": 1, "operator": 2, "coordinator": 3}
DEFAULT_ROLE_PERMISSIONS = {
    "viewer": ["access.viewer", "dashboard.view", "students.view"],
    "operator": ["access.viewer", "access.operator", "dashboard.view", "students.view",
        "students.create", "students.edit", "campaigns.view", "campaigns.create",
        "campaigns.edit", "members.view", "data.view"],
    "coordinator": ["access.viewer", "access.operator", "access.coordinator", "dashboard.view",
        "students.view", "students.sensitive.view", "students.create", "students.edit",
        "campaigns.view", "campaigns.create", "campaigns.edit", "campaigns.approve",
        "campaigns.execute", "members.view", "members.manage", "data.view", "data.import",
        "audit.view"],
    "admin": list(PERMISSION_CATALOG.keys()),
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _require_admin(auth: AuthContext, *, recent: bool = False) -> str:
    if not auth.user_id:
        raise HTTPException(status_code=403, detail="Esta operação exige uma sessão humana.")
    builtin_admin = auth.role == "admin" and not auth.custom_role_id
    delegated_manager = auth.permissions is not None and "permissions.manage" in auth.permissions
    if not builtin_admin and not delegated_manager:
        raise HTTPException(status_code=403, detail="Você não tem permissão para administrar cargos.")
    if recent and (auth.aal < 2 or not auth.authenticated_at or int(_now().timestamp()) - auth.authenticated_at > 600):
        raise HTTPException(status_code=403, detail="Confirme novamente sua identidade com MFA antes desta operação.")
    return auth.user_id


def _validate_actor_grants(auth: AuthContext, base_role: str, permissions: list[str]) -> None:
    if auth.role == "admin" and not auth.custom_role_id:
        return
    if BASE_ROLE_RANK.get(base_role, 99) > BASE_ROLE_RANK.get(auth.role or "viewer", 0):
        raise HTTPException(status_code=403, detail="Você não pode atribuir um cargo-base superior ao seu.")
    if auth.permissions is None or not set(permissions).issubset(auth.permissions):
        raise HTTPException(status_code=403, detail="Você só pode delegar permissões que já possui.")


def _audit(db: AsyncSession, auth: AuthContext, event: str, *, role_id: str | None = None,
           target_user_id: str | None = None, details: dict | None = None) -> None:
    db.add(TenantRoleAudit(
        tenant_id=auth.tenant_id, actor_user_id=auth.user_id, target_user_id=target_user_id,
        role_id=role_id, event_type=event, details=details or {},
    ))


def _role_dict(role: TenantRole, members_count: int = 0) -> dict:
    return {
        "id": role.id, "name": role.name, "description": role.description,
        "base_role": role.base_role, "permissions": role.permissions or [],
        "is_active": role.is_active, "members_count": members_count,
        "created_at": role.created_at.isoformat() if role.created_at else None,
        "updated_at": role.updated_at.isoformat() if role.updated_at else None,
    }


_PERMISSION_CEILING = {
    "access.viewer": 1, "dashboard.view": 1, "students.view": 1,
    "access.operator": 2, "students.create": 2, "students.edit": 2,
    "campaigns.view": 2, "campaigns.create": 2, "campaigns.edit": 2,
    "members.view": 2, "data.view": 2,
    "access.coordinator": 3, "data.import": 3, "audit.view": 3,
    "students.sensitive.view": 3, "campaigns.approve": 3,
    "campaigns.execute": 3, "members.manage": 3,
    "permissions.manage": 3, "settings.manage": 3,
    "students.delete": 3, "campaigns.delete": 3, "critical.manage": 3,
}


def _validate_permission_ceiling(base_role: str, permissions: list[str]) -> None:
    ceiling = BASE_ROLE_RANK[base_role]
    if any(_PERMISSION_CEILING.get(permission, 99) > ceiling for permission in permissions):
        raise HTTPException(
            status_code=422,
            detail="O cargo personalizado não pode conceder permissões acima do seu cargo-base.",
        )


class RolePayload(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    description: Optional[str] = Field(default=None, max_length=500)
    base_role: str = Field(default="viewer")
    permissions: list[str] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = " ".join(value.split()).strip()
        if not value:
            raise ValueError("Informe o nome do cargo.")
        return value

    @field_validator("base_role")
    @classmethod
    def safe_base_role(cls, value: str) -> str:
        if value not in BASE_ROLE_RANK:
            raise ValueError("Cargo-base inválido. O papel admin não pode ser personalizado.")
        return value

    @field_validator("permissions")
    @classmethod
    def valid_permissions(cls, value: list[str]) -> list[str]:
        normalized = sorted(set(value) | {"access.viewer"})
        unknown = set(normalized) - set(PERMISSION_CATALOG)
        if unknown:
            raise ValueError("A lista contém permissões desconhecidas.")
        return normalized


async def _load_role(db: AsyncSession, tenant_id: str, role_id: str, *, lock: bool = False) -> TenantRole:
    query = select(TenantRole).where(TenantRole.id == role_id, TenantRole.tenant_id == tenant_id)
    if lock:
        query = query.with_for_update()
    role = (await db.execute(query)).scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=404, detail="Cargo não encontrado nesta instituição.")
    return role


@router.get("/roles/catalog")
async def permission_catalog(auth: AuthContext = Depends(get_current_tenant)):
    return {"permissions": [{"key": key, "label": label} for key, label in PERMISSION_CATALOG.items()]}


@router.get("/roles")
async def list_roles(auth: AuthContext = Depends(get_current_tenant), db: AsyncSession = Depends(get_db)):
    _require_admin(auth)
    roles = (await db.execute(
        select(TenantRole).where(TenantRole.tenant_id == auth.tenant_id).order_by(TenantRole.name.asc())
    )).scalars().all()
    counts = dict((await db.execute(
        select(User.custom_role_id, func.count(User.id))
        .where(User.tenant_id == auth.tenant_id, User.custom_role_id.is_not(None))
        .group_by(User.custom_role_id)
    )).all())
    return {"roles": [_role_dict(role, int(counts.get(role.id, 0))) for role in roles]}


@router.post("/roles", status_code=status.HTTP_201_CREATED)
async def create_role(body: RolePayload, auth: AuthContext = Depends(get_current_tenant),
                      db: AsyncSession = Depends(get_db)):
    actor = _require_admin(auth, recent=True)
    _validate_permission_ceiling(body.base_role, body.permissions)
    _validate_actor_grants(auth, body.base_role, body.permissions)
    duplicate = await db.execute(select(TenantRole.id).where(
        TenantRole.tenant_id == auth.tenant_id, func.lower(TenantRole.name) == body.name.lower()
    ))
    if duplicate.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Já existe um cargo com esse nome.")
    role = TenantRole(
        tenant_id=auth.tenant_id, name=body.name, description=body.description,
        base_role=body.base_role, permissions=body.permissions, created_by_user_id=actor,
    )
    db.add(role)
    await db.flush()
    _audit(db, auth, "role.created", role_id=role.id,
           details={"name": role.name, "base_role": role.base_role, "permissions": role.permissions})
    await db.commit()
    await db.refresh(role)
    return {"role": _role_dict(role)}


@router.patch("/roles/{role_id}")
async def update_role(role_id: str, body: RolePayload, auth: AuthContext = Depends(get_current_tenant),
                      db: AsyncSession = Depends(get_db)):
    _require_admin(auth, recent=True)
    _validate_permission_ceiling(body.base_role, body.permissions)
    _validate_actor_grants(auth, body.base_role, body.permissions)
    role = await _load_role(db, auth.tenant_id, role_id, lock=True)
    _validate_actor_grants(auth, role.base_role, list(role.permissions or []))
    if not role.is_active:
        raise HTTPException(status_code=409, detail="Reative o cargo antes de editá-lo.")
    conflict = await db.execute(select(TenantRole.id).where(
        TenantRole.tenant_id == auth.tenant_id, func.lower(TenantRole.name) == body.name.lower(),
        TenantRole.id != role.id,
    ))
    if conflict.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Já existe outro cargo com esse nome.")
    before = {"name": role.name, "base_role": role.base_role, "permissions": role.permissions}
    role.name, role.description = body.name, body.description
    role.base_role, role.permissions = body.base_role, body.permissions
    _audit(db, auth, "role.updated", role_id=role.id, details={"before": before,
           "after": {"name": role.name, "base_role": role.base_role, "permissions": role.permissions}})
    await db.commit()
    await db.refresh(role)
    return {"role": _role_dict(role)}


@router.post("/roles/{role_id}/duplicate", status_code=status.HTTP_201_CREATED)
async def duplicate_role(role_id: str, auth: AuthContext = Depends(get_current_tenant),
                         db: AsyncSession = Depends(get_db)):
    actor = _require_admin(auth, recent=True)
    source = await _load_role(db, auth.tenant_id, role_id)
    _validate_actor_grants(auth, source.base_role, list(source.permissions or []))
    if not source.is_active:
        raise HTTPException(status_code=409, detail="Não é possível duplicar um cargo desativado.")
    name = f"{source.name} (cópia)"
    exists = await db.execute(select(TenantRole.id).where(
        TenantRole.tenant_id == auth.tenant_id, func.lower(TenantRole.name) == name.lower()
    ))
    if exists.scalar_one_or_none():
        name = f"{source.name} (cópia {str(uuid4())[:8]})"
    clone = TenantRole(tenant_id=auth.tenant_id, name=name, description=source.description,
        base_role=source.base_role, permissions=list(source.permissions or []), created_by_user_id=actor)
    db.add(clone)
    await db.flush()
    _audit(db, auth, "role.duplicated", role_id=clone.id, details={"source_role_id": source.id})
    await db.commit()
    await db.refresh(clone)
    return {"role": _role_dict(clone)}


@router.post("/roles/{role_id}/deactivate")
async def deactivate_role(role_id: str, auth: AuthContext = Depends(get_current_tenant),
                          db: AsyncSession = Depends(get_db)):
    _require_admin(auth, recent=True)
    role = await _load_role(db, auth.tenant_id, role_id, lock=True)
    _validate_actor_grants(auth, role.base_role, list(role.permissions or []))
    assigned = await db.execute(select(func.count(User.id)).where(
        User.tenant_id == auth.tenant_id, User.custom_role_id == role.id, User.is_active.is_(True)
    ))
    if (assigned.scalar() or 0) > 0:
        raise HTTPException(status_code=409, detail="Reatribua os membros antes de desativar este cargo.")
    role.is_active = False
    _audit(db, auth, "role.deactivated", role_id=role.id)
    await db.commit()
    return {"deactivated": True, "role_id": role.id}


@router.get("/roles/{role_id}/members")
async def role_members(role_id: str, auth: AuthContext = Depends(get_current_tenant),
                       db: AsyncSession = Depends(get_db)):
    _require_admin(auth)
    role = await _load_role(db, auth.tenant_id, role_id)
    users = (await db.execute(select(User).where(
        User.tenant_id == auth.tenant_id, User.custom_role_id == role.id
    ).order_by(User.display_name.asc()))).scalars().all()
    return {"role": _role_dict(role, len(users)), "members": [
        {"id": u.id, "display_name": u.display_name, "email": u.email, "status": "active" if u.is_active else "disabled"}
        for u in users
    ]}


@router.post("/members/{user_id}/role")
async def assign_member_role(user_id: str, body: dict, auth: AuthContext = Depends(get_current_tenant),
                             db: AsyncSession = Depends(get_db)):
    _require_admin(auth, recent=True)
    role_id = body.get("custom_role_id")
    if role_id is not None and not isinstance(role_id, str):
        raise HTTPException(status_code=422, detail="custom_role_id inválido.")
    target = (await db.execute(select(User).where(
        User.id == user_id, User.tenant_id == auth.tenant_id
    ).with_for_update())).scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="Membro não encontrado nesta instituição.")
    if target.role == "admin":
        raise HTTPException(status_code=409, detail="A administração principal não pode ser substituída por cargo personalizado.")
    new_role = await _load_role(db, auth.tenant_id, role_id) if role_id else None
    if new_role and auth.role != "admin" and (
        BASE_ROLE_RANK.get(new_role.base_role, 99) > BASE_ROLE_RANK.get(auth.role or "viewer", 0)
        or auth.permissions is None
        or not set(new_role.permissions or []).issubset(auth.permissions)
    ):
        raise HTTPException(status_code=403, detail="Você não pode atribuir um cargo com privilégios que não possui.")
    if new_role and not new_role.is_active:
        raise HTTPException(status_code=409, detail="O cargo selecionado está desativado.")
    old_role_id = target.custom_role_id
    target.custom_role_id = new_role.id if new_role else None
    if new_role:
        target.role = new_role.base_role
    else:
        # Revogar um cargo personalizado nunca eleva o membro.
        target.role = "viewer"
    target.auth_version += 1

    # Dual-write: keep Membership in sync with User.role / custom_role_id
    synced = await sync_membership_role(
        db,
        user_id=target.id,
        tenant_id=auth.tenant_id,
        role=target.role,
        custom_role_id=target.custom_role_id,
    )
    if synced is None:
        # Membership may not exist yet for legacy users — create it
        await ensure_membership(
            db,
            user=target,
            tenant_id=auth.tenant_id,
            role=target.role,
            custom_role_id=target.custom_role_id,
            origin="role_assignment",
            status="active" if target.is_active else "suspended",
        )

    _audit(db, auth, "member.role_assigned" if new_role else "member.role_revoked",
           role_id=new_role.id if new_role else old_role_id, target_user_id=target.id,
           details={"previous_role_id": old_role_id, "new_role_id": new_role.id if new_role else None})
    await db.commit()
    return {"member_id": target.id, "custom_role_id": target.custom_role_id,
            "base_role": target.role, "sessions_invalidated": True}


@router.get("/members/{user_id}/permissions")
async def member_effective_permissions(user_id: str, auth: AuthContext = Depends(get_current_tenant),
                                       db: AsyncSession = Depends(get_db)):
    _require_admin(auth)
    user = (await db.execute(select(User).where(
        User.id == user_id, User.tenant_id == auth.tenant_id
    ))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Membro não encontrado nesta instituição.")
    role = await _load_role(db, auth.tenant_id, user.custom_role_id) if user.custom_role_id else None
    if role:
        base_rank = BASE_ROLE_RANK.get(role.base_role, 0)
        permissions = sorted(
            permission for permission in (role.permissions or [])
            if _PERMISSION_CEILING.get(permission, 99) <= base_rank
        ) if role.is_active else []
    else:
        permissions = sorted(DEFAULT_ROLE_PERMISSIONS.get(user.role, DEFAULT_ROLE_PERMISSIONS["viewer"]))
    return {"member_id": user.id, "legacy_role": user.role,
            "custom_role": _role_dict(role) if role else None,
            "permissions": permissions, "custom_role_active": bool(role.is_active) if role else True}


@router.get("/role-audit")
async def role_audit(auth: AuthContext = Depends(get_current_tenant), db: AsyncSession = Depends(get_db)):
    _require_admin(auth)
    rows = (await db.execute(select(TenantRoleAudit).where(
        TenantRoleAudit.tenant_id == auth.tenant_id
    ).order_by(TenantRoleAudit.created_at.desc()).limit(200))).scalars().all()
    return {"events": [{"id": row.id, "event_type": row.event_type, "actor_user_id": row.actor_user_id,
        "target_user_id": row.target_user_id, "role_id": row.role_id, "details": row.details,
        "created_at": row.created_at.isoformat()} for row in rows]}
