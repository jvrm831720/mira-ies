"""Organização: membros e convites por e-mail + papel."""
from __future__ import annotations

import logging
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.channels.whatsapp import normalize_phone_br
from app.agents.providers.resend_provider import send_email_resend
from app.core.auth import AuthContext, ROLE_RANK, get_current_tenant, require_min_role
from app.core.config import get_settings
from app.core.mira_security import hash_password
from app.core.security import hash_api_key
from app.db.session import get_db
from app.models.auth import OrganizationInvite, TenantRole, TenantRoleAudit, User, UserSession
from app.api.mfa import create_login_challenge
from app.core.mfa_policy import user_requires_mfa
from app.core.user_sessions import create_user_session
from app.models.organization import Membership
from app.models.tenant import Tenant
from app.services.membership import ensure_membership, get_membership_for_tenant, list_active_memberships

router = APIRouter(prefix="/org", tags=["Organização / Membros"])
logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_VALID_ROLES = ("admin", "coordinator", "operator", "viewer")
_INVITE_TTL_DAYS = 7


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_email(value: str) -> str:
    normalized = value.strip().lower()
    if not _EMAIL_RE.fullmatch(normalized):
        raise ValueError("Informe um e-mail válido.")
    return normalized


def _invite_token_hash(token: str) -> str:
    return hash_api_key(f"mira:org-invite:{token}")


class InviteCreatePayload(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    role: Literal["admin", "coordinator", "operator", "viewer"] = "coordinator"
    custom_role_id: Optional[str] = Field(default=None, max_length=36)

    @field_validator("email")
    @classmethod
    def email_ok(cls, value: str) -> str:
        return _normalize_email(value)


class AcceptInvitePayload(BaseModel):
    token: str = Field(min_length=16, max_length=512)
    password: str = Field(min_length=8, max_length=256)
    phone: str = Field(min_length=8, max_length=30)
    display_name: Optional[str] = Field(default=None, max_length=120)


class AcceptExistingInvitePayload(BaseModel):
    token: str = Field(min_length=16, max_length=512)


class SwitchWorkspacePayload(BaseModel):
    """Switch active workspace by membership_id or tenant_id."""
    membership_id: Optional[str] = Field(default=None, max_length=36)
    tenant_id: Optional[str] = Field(default=None, max_length=36)


def _member_dict(user: User, membership: Membership | None = None) -> dict:
    role = membership.role if membership else user.role
    status_value = membership.status if membership else ("active" if user.is_active else "disabled")
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "role": role if role in _VALID_ROLES else "coordinator",
        "custom_role_id": membership.custom_role_id if membership else user.custom_role_id,
        "status": status_value if user.is_active else "disabled",
        "phone": user.phone_e164,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


def _invite_dict(inv: OrganizationInvite, invite_url: Optional[str] = None) -> dict:
    data = {
        "id": inv.id,
        "email": inv.email,
        "role": inv.role,
        "custom_role_id": inv.custom_role_id,
        "status": inv.status,
        "created_at": inv.created_at.isoformat() if inv.created_at else None,
        "expires_at": inv.expires_at.isoformat() if inv.expires_at else None,
    }
    if invite_url:
        data["invite_url"] = invite_url
    return data


@router.get("/members")
async def list_members(
    auth: AuthContext = Depends(require_min_role("operator")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(Membership.tenant_id == auth.tenant_id)
        .order_by(User.created_at.asc())
    )
    members = result.all()
    return {
        "organization_name": auth.tenant.name,
        "members": [_member_dict(user, membership) for membership, user in members],
    }


@router.get("/invites")
async def list_invites(
    auth: AuthContext = Depends(require_min_role("coordinator")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(OrganizationInvite)
        .where(
            OrganizationInvite.tenant_id == auth.tenant_id,
            OrganizationInvite.status == "pending",
        )
        .order_by(OrganizationInvite.created_at.desc())
    )
    invites = result.scalars().all()
    now = _now()
    out = []
    for inv in invites:
        if inv.expires_at and inv.expires_at <= now:
            inv.status = "expired"
            continue
        out.append(_invite_dict(inv))
    await db.commit()
    return {"invites": out}


@router.post("/invites", status_code=status.HTTP_201_CREATED)
async def create_invite(
    body: InviteCreatePayload,
    auth: AuthContext = Depends(require_min_role("coordinator")),
    db: AsyncSession = Depends(get_db),
):
    settings = get_settings()

    if body.role == "admin":
        if auth.role != "admin" or not auth.user_id:
            raise HTTPException(status_code=403, detail="Somente um administrador pode conceder o papel admin.")
        if auth.aal < 2 or not auth.authenticated_at or int(_now().timestamp()) - auth.authenticated_at > 600:
            raise HTTPException(status_code=403, detail="Confirme novamente sua identidade com MFA antes de conceder admin.")
    if body.custom_role_id and body.role == "admin":
        raise HTTPException(status_code=422, detail="Um convite não pode combinar admin com cargo personalizado.")
    custom_role = None
    if auth.custom_role_id and not body.custom_role_id:
        raise HTTPException(status_code=403, detail="Cargos personalizados só podem convidar membros para cargos que já possuem.")
    if body.custom_role_id:
        custom_role = (await db.execute(select(TenantRole).where(
            TenantRole.id == body.custom_role_id,
            TenantRole.tenant_id == auth.tenant_id,
            TenantRole.is_active.is_(True),
        ))).scalar_one_or_none()
        if not custom_role:
            raise HTTPException(status_code=404, detail="Cargo personalizado não encontrado ou desativado.")
        if auth.role != "admin" and auth.permissions is None:
            raise HTTPException(status_code=403, detail="Somente administradores ou delegados podem convidar para cargos personalizados.")
        if body.role == "admin":
            raise HTTPException(status_code=422, detail="Convites com cargo personalizado não podem conceder admin.")
        if auth.custom_role_id and (
            ROLE_RANK.get(custom_role.base_role, 99) > ROLE_RANK.get(auth.role or "viewer", 0)
            or auth.permissions is None
            or not set(custom_role.permissions or []).issubset(auth.permissions)
        ):
            raise HTTPException(status_code=403, detail="Você não pode convidar alguém com privilégios que não possui.")
    existing_user = (await db.execute(select(User).where(User.email == body.email))).scalar_one_or_none()
    if existing_user:
        existing_membership = await get_membership_for_tenant(
            db, user_id=existing_user.id, tenant_id=auth.tenant_id
        )
        if existing_membership and existing_membership.status == "active":
            raise HTTPException(status_code=409, detail="Esta conta já tem acesso ativo a esta instituição.")

    pending = await db.execute(
        select(OrganizationInvite).where(
            OrganizationInvite.tenant_id == auth.tenant_id,
            OrganizationInvite.email == body.email,
            OrganizationInvite.status == "pending",
        )
    )
    old = pending.scalar_one_or_none()
    if old:
        old.status = "revoked"

    raw_token = secrets.token_urlsafe(32)
    invite = OrganizationInvite(
        tenant_id=auth.tenant_id,
        email=body.email,
        role=custom_role.base_role if custom_role else body.role,
        custom_role_id=custom_role.id if custom_role else None,
        token_hash=_invite_token_hash(raw_token),
        status="pending",
        invited_by_user_id=auth.user_id,
        expires_at=_now() + timedelta(days=_INVITE_TTL_DAYS),
    )
    db.add(invite)
    db.add(TenantRoleAudit(
        tenant_id=auth.tenant_id,
        actor_user_id=auth.user_id,
        role_id=custom_role.id if custom_role else None,
        event_type="member.role_invited",
        details={"invite_id": invite.id, "base_role": invite.role, "custom_role_id": invite.custom_role_id},
    ))
    await db.commit()
    await db.refresh(invite)

    invite_url = f"{settings.mira_public_url.rstrip('/')}/convite/{raw_token}"

    emailed = False
    if settings.resend_api_key and settings.email_from:
        if existing_user:
            access_instructions = "Entre na sua conta MIRA existente e aceite o convite pelo link abaixo."
        else:
            access_instructions = "Abra o link abaixo para criar sua senha e telefone."
        body_text = (
            f"Você foi convidado(a) para a organização {auth.tenant.name} na Mira.\n\n"
            f"Perfil de acesso: {body.role}\n\n"
            f"{access_instructions} O convite é válido por {_INVITE_TTL_DAYS} dias:\n\n"
            f"{invite_url}\n\n"
            f"Se você não esperava este convite, ignore este e-mail."
        )
        delivery = await send_email_resend(
            to=body.email,
            subject=f"Convite Mira — {auth.tenant.name}",
            body=body_text,
        )
        emailed = bool(delivery.ok)
        if not delivery.ok:
            logger.warning("Falha ao enviar convite por e-mail para %s", body.email)

    return {
        "message": (
            "Convite criado e e-mail enviado."
            if emailed
            else "Convite criado. O link foi gerado para compartilhamento seguro com o convidado."
        ),
        "invite": _invite_dict(invite, invite_url=invite_url),
        "invite_url": invite_url,
        "recipient_has_account": existing_user is not None,
    }


@router.post("/invites/accept")
async def accept_invite(
    body: AcceptInvitePayload,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    token_hash = _invite_token_hash(body.token.strip())
    result = await db.execute(
        select(OrganizationInvite)
        .where(
            OrganizationInvite.token_hash == token_hash,
            OrganizationInvite.status == "pending",
        )
        .limit(1)
        .with_for_update()
    )
    invite = result.scalar_one_or_none()
    now = _now()
    if not invite or invite.expires_at <= now:
        if invite and invite.expires_at <= now:
            invite.status = "expired"
            await db.commit()
        raise HTTPException(status_code=400, detail="Convite inválido ou expirado.")

    tenant = await db.get(Tenant, invite.tenant_id)
    if not tenant or not tenant.is_active:
        raise HTTPException(status_code=400, detail="Organização indisponível.")

    existing = await db.execute(select(User.id).where(User.email == invite.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Já existe uma conta com esse e-mail.")

    phone = normalize_phone_br(body.phone)
    if not phone:
        raise HTTPException(status_code=422, detail="Informe um telefone válido com DDD.")

    phone_taken = await db.execute(select(User.id).where(User.phone_e164 == phone))
    if phone_taken.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Este telefone já está em uso.")

    display = (body.display_name or "").strip() or invite.email.split("@")[0]
    custom_role = None
    if invite.custom_role_id:
        custom_role = (await db.execute(select(TenantRole).where(
            TenantRole.id == invite.custom_role_id,
            TenantRole.tenant_id == invite.tenant_id,
            TenantRole.is_active.is_(True),
        ))).scalar_one_or_none()
        if not custom_role:
            raise HTTPException(status_code=400, detail="O cargo deste convite foi desativado. Solicite um novo convite.")
    user = User(
        tenant_id=invite.tenant_id,
        display_name=display[:120],
        email=invite.email,
        phone_e164=phone,
        password_hash=hash_password(body.password),
        role=custom_role.base_role if custom_role else (invite.role if invite.role in _VALID_ROLES else "coordinator"),
        custom_role_id=custom_role.id if custom_role else None,
        is_active=True,
    )
    db.add(user)
    invite.status = "accepted"
    invite.accepted_at = now
    await db.flush()
    await db.execute(text("SELECT set_config('app.user_id', :user_id, true)"), {"user_id": user.id})
    await db.execute(text("SELECT set_config('app.tenant_id', :tenant_id, true)"), {"tenant_id": tenant.id})
    await ensure_membership(
        db,
        user=user,
        tenant_id=invite.tenant_id,
        role=user.role,
        custom_role_id=user.custom_role_id,
        origin="invite",
        status="active",
    )
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Não foi possível ativar o acesso.")
    await db.refresh(user)

    if await user_requires_mfa(db, user):
        return await create_login_challenge(db, user, tenant, purpose="enroll")
    token, ttl = await create_user_session(db, user, tenant, request, aal=1)
    await db.commit()
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": ttl,
        "user": {
            "display_name": user.display_name,
            "email": user.email,
            "tenant_name": tenant.name,
        },
    }


@router.post("/invites/accept-existing")
async def accept_existing_invite(
    body: AcceptExistingInvitePayload,
    request: Request,
    auth: AuthContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Attach an authenticated global identity to an invited workspace."""
    if not auth.user_id or not auth.session_id:
        raise HTTPException(status_code=401, detail="Entre na sua conta para aceitar este convite.")
    user = await db.get(User, auth.user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Conta inativa ou inexistente.")

    token_hash = _invite_token_hash(body.token.strip())
    invite = (
        await db.execute(
            select(OrganizationInvite)
            .where(
                OrganizationInvite.token_hash == token_hash,
                OrganizationInvite.status == "pending",
            )
            .limit(1)
            .with_for_update()
        )
    ).scalar_one_or_none()
    now = _now()
    if not invite or invite.expires_at <= now:
        if invite and invite.expires_at <= now:
            invite.status = "expired"
            await db.commit()
        raise HTTPException(status_code=400, detail="Convite inválido ou expirado.")
    if user.email.strip().lower() != invite.email.strip().lower():
        raise HTTPException(status_code=403, detail="O convite foi enviado para outro e-mail.")

    tenant = await db.get(Tenant, invite.tenant_id)
    if not tenant or not tenant.is_active:
        raise HTTPException(status_code=400, detail="Organização indisponível.")
    if invite.role == "admin" and (
        auth.aal < 2
        or not auth.authenticated_at
        or int(now.timestamp()) - auth.authenticated_at > 600
    ):
        raise HTTPException(status_code=403, detail="Confirme novamente sua identidade com MFA para aceitar admin.")

    old_session = (
        await db.execute(
            select(UserSession)
            .where(
                UserSession.id == auth.session_id,
                UserSession.user_id == user.id,
                UserSession.tenant_id == auth.tenant_id,
                UserSession.revoked_at.is_(None),
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if not old_session:
        raise HTTPException(status_code=401, detail="Sessão encerrada. Entre novamente.")

    # Validate the custom role under the destination tenant context.
    await db.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": tenant.id},
    )
    custom_role = None
    if invite.custom_role_id:
        custom_role = (
            await db.execute(
                select(TenantRole).where(
                    TenantRole.id == invite.custom_role_id,
                    TenantRole.tenant_id == tenant.id,
                    TenantRole.is_active.is_(True),
                )
            )
        ).scalar_one_or_none()
        if not custom_role:
            raise HTTPException(status_code=400, detail="O cargo deste convite foi desativado. Solicite um novo convite.")

    # Revoke the current session before committing the destination session.
    old_session.revoked_at = now
    old_session.revoked_by_user_id = user.id
    old_session.revoke_reason = "invite_accepted_workspace_switch"

    role = custom_role.base_role if custom_role else (invite.role if invite.role in _VALID_ROLES else "coordinator")
    membership = await ensure_membership(
        db,
        user=user,
        tenant_id=tenant.id,
        role=role,
        custom_role_id=custom_role.id if custom_role else None,
        origin="invite_existing_account",
        status="active",
    )
    invite.status = "accepted"
    invite.accepted_at = now
    db.add(
        TenantRoleAudit(
            tenant_id=tenant.id,
            actor_user_id=user.id,
            target_user_id=user.id,
            role_id=custom_role.id if custom_role else None,
            event_type="member.invite_accepted",
            details={"invite_id": invite.id, "membership_id": membership.id},
        )
    )
    token, ttl = await create_user_session(
        db,
        user,
        tenant,
        request,
        aal=auth.aal,
        authenticated_at=auth.authenticated_at,
        membership=membership,
    )
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Não foi possível aceitar o convite.")
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": ttl,
        "tenant_id": tenant.id,
        "tenant_name": tenant.name,
        "membership_id": membership.id,
        "role": membership.role,
        "user": {"display_name": user.display_name, "email": user.email, "tenant_name": tenant.name},
    }


@router.get("/me")
async def me(auth: AuthContext = Depends(get_current_tenant), db: AsyncSession = Depends(get_db)):
    """Perfil da sessão atual (papel + instituição + onboarding)."""
    user = await db.get(User, auth.user_id) if auth.user_id else None
    completed_at = getattr(user, "onboarding_completed_at", None) if user else None
    return {
        "tenant_id": auth.tenant_id,
        "tenant_name": auth.tenant.name,
        "tenant_slug": auth.tenant_slug,
        "user_id": auth.user_id,
        "role": auth.role or (user.role if user else "admin"),
        "custom_role_id": auth.custom_role_id,
        "permissions": sorted(auth.permissions) if auth.permissions is not None else None,
        "display_name": user.display_name if user else None,
        "email": user.email if user else None,
        "membership_id": auth.membership_id,
        "onboarding_completed": bool(completed_at),
        "onboarding_completed_at": completed_at.isoformat() if completed_at else None,
    }


@router.post("/me/onboarding/complete")
async def complete_onboarding(
    auth: AuthContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Marca o onboarding institucional como concluído para o usuário autenticado."""
    if not auth.user_id:
        raise HTTPException(status_code=400, detail="Sessão sem usuário associado.")
    user = await db.get(User, auth.user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=404, detail="Usuário não encontrado nesta instituição.")
    if not user.onboarding_completed_at:
        user.onboarding_completed_at = _now()
        await db.commit()
        await db.refresh(user)
    return {
        "onboarding_completed": True,
        "onboarding_completed_at": user.onboarding_completed_at.isoformat()
        if user.onboarding_completed_at
        else None,
    }


# ---------------------------------------------------------------------------
# Phase C — Workspaces (membership-aware list + switch)
# ---------------------------------------------------------------------------


@router.get("/workspaces")
async def list_workspaces(
    auth: AuthContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Lista workspaces (tenants) aos quais o usuário autenticado tem membership ativa.

    Inclui fallback legado (User.tenant_id) quando ainda não há Membership.
    """
    if not auth.user_id:
        raise HTTPException(status_code=400, detail="Sessão sem usuário associado.")

    user = await db.get(User, auth.user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Usuário inativo ou inexistente.")

    memberships = await list_active_memberships(db, user.id)
    workspaces: list[dict] = []
    seen_tenant_ids: set[str] = set()

    for m in memberships:
        tenant = await db.get(Tenant, m.tenant_id)
        if not tenant or not tenant.is_active:
            continue
        seen_tenant_ids.add(tenant.id)
        workspaces.append(
            {
                "membership_id": m.id,
                "tenant_id": tenant.id,
                "tenant_name": tenant.name,
                "tenant_slug": tenant.slug,
                "role": m.role if m.role in _VALID_ROLES else "coordinator",
                "custom_role_id": m.custom_role_id,
                "status": m.status,
                "is_current": tenant.id == auth.tenant_id,
                "origin": m.origin,
            }
        )

    # Legacy fallback is valid only when no Membership row exists at all.
    legacy_membership = (
        await get_membership_for_tenant(db, user_id=user.id, tenant_id=user.tenant_id)
        if user.tenant_id else None
    )
    if user.tenant_id and not legacy_membership and user.tenant_id not in seen_tenant_ids:
        tenant = await db.get(Tenant, user.tenant_id)
        if tenant and tenant.is_active:
            workspaces.append(
                {
                    "membership_id": None,
                    "tenant_id": tenant.id,
                    "tenant_name": tenant.name,
                    "tenant_slug": tenant.slug,
                    "role": user.role if user.role in _VALID_ROLES else "coordinator",
                    "custom_role_id": user.custom_role_id,
                    "status": "active" if user.is_active else "suspended",
                    "is_current": tenant.id == auth.tenant_id,
                    "origin": "legacy_user",
                }
            )

    # Ensure current workspace appears even if somehow missing
    if auth.tenant_id and auth.tenant_id not in {w["tenant_id"] for w in workspaces}:
        workspaces.insert(
            0,
            {
                "membership_id": auth.membership_id,
                "tenant_id": auth.tenant_id,
                "tenant_name": auth.tenant.name,
                "tenant_slug": auth.tenant_slug,
                "role": auth.role or "viewer",
                "custom_role_id": auth.custom_role_id,
                "status": "active",
                "is_current": True,
                "origin": "session",
            },
        )

    # Current first, then alphabetical
    workspaces.sort(key=lambda w: (not w["is_current"], (w["tenant_name"] or "").lower()))

    return {
        "current_tenant_id": auth.tenant_id,
        "current_membership_id": auth.membership_id,
        "workspaces": workspaces,
    }


@router.post("/workspaces/switch")
async def switch_workspace(
    body: SwitchWorkspacePayload,
    request: Request,
    auth: AuthContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Troca o workspace ativo da sessão.

    - Valida que o usuário tem membership ativa no destino.
    - Revoga a sessão atual.
    - Emite novo JWT com tid/mid do workspace escolhido (mesmo AAL).
    - Cross-tenant isolation: só memberships do próprio user_id.
    """
    if not auth.user_id:
        raise HTTPException(status_code=400, detail="Sessão sem usuário associado.")
    if not body.membership_id and not body.tenant_id:
        raise HTTPException(status_code=422, detail="Informe membership_id ou tenant_id.")

    user = await db.get(User, auth.user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Usuário inativo ou inexistente.")

    target_membership: Optional[Membership] = None
    target_tenant: Optional[Tenant] = None

    if body.membership_id:
        result = await db.execute(
            select(Membership).where(
                Membership.id == body.membership_id,
                Membership.user_id == user.id,
                Membership.status == "active",
            ).with_for_update()
        )
        target_membership = result.scalar_one_or_none()
        if not target_membership:
            raise HTTPException(status_code=404, detail="Membership não encontrada ou inativa.")
        target_tenant = await db.get(Tenant, target_membership.tenant_id)
    else:
        # Resolve by tenant_id — only if user has active membership there
        target_membership = await get_membership_for_tenant(
            db, user_id=user.id, tenant_id=body.tenant_id, for_update=True
        )
        if target_membership:
            if target_membership.status != "active":
                raise HTTPException(status_code=403, detail="Membership inativa neste workspace.")
            target_tenant = await db.get(Tenant, target_membership.tenant_id)
        elif user.tenant_id == body.tenant_id:
            # Legacy path: ensure membership then switch
            target_tenant = await db.get(Tenant, body.tenant_id)
            if target_tenant and target_tenant.is_active:
                target_membership = await ensure_membership(
                    db,
                    user=user,
                    tenant_id=target_tenant.id,
                    role=user.role or "coordinator",
                    custom_role_id=user.custom_role_id,
                    origin="workspace_switch",
                    status="active",
                )

    if not target_tenant or not target_tenant.is_active:
        raise HTTPException(status_code=404, detail="Workspace não encontrado ou inativo.")
    if not target_membership:
        raise HTTPException(
            status_code=403,
            detail="Você não tem acesso a este workspace.",
        )

    # Already on this workspace — return current token shape without churn
    if target_tenant.id == auth.tenant_id and (
        not body.membership_id or body.membership_id == auth.membership_id
    ):
        return {
            "switched": False,
            "message": "Já está neste workspace.",
            "tenant_id": auth.tenant_id,
            "tenant_name": auth.tenant.name,
            "membership_id": auth.membership_id,
        }

    # Revoke current session (force re-bind to new tid/mid)
    session = (
        await db.execute(
            select(UserSession)
            .where(
                UserSession.id == auth.session_id,
                UserSession.user_id == user.id,
                UserSession.tenant_id == auth.tenant_id,
                UserSession.revoked_at.is_(None),
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=401, detail="Sessão encerrada. Entre novamente.")
    session.revoked_at = _now()
    session.revoked_by_user_id = user.id
    session.revoke_reason = "workspace_switch"

    # Issue new session bound to target tenant + membership
    # Keep the same AAL so MFA step-up is not lost
    aal = max(1, int(auth.aal or 1))
    token, ttl = await create_user_session(
        db,
        user,
        target_tenant,
        request,
        aal=aal,
        authenticated_at=auth.authenticated_at,
        membership=target_membership,
    )
    await db.commit()

    return {
        "switched": True,
        "access_token": token,
        "token_type": "bearer",
        "expires_in": ttl,
        "tenant_id": target_tenant.id,
        "tenant_name": target_tenant.name,
        "tenant_slug": target_tenant.slug,
        "membership_id": target_membership.id,
        "role": target_membership.role,
        "user": {
            "display_name": user.display_name,
            "email": user.email,
            "tenant_name": target_tenant.name,
        },
    }
