"""Organização: membros e convites por e-mail + papel."""
from __future__ import annotations

import logging
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.channels.whatsapp import normalize_phone_br
from app.agents.providers.resend_provider import send_email_resend
from app.core.auth import AuthContext, get_current_tenant
from app.core.config import get_settings
from app.core.mira_security import hash_password, issue_access_token
from app.core.security import hash_api_key
from app.db.session import get_db
from app.models.auth import OrganizationInvite, User
from app.models.tenant import Tenant

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


async def _require_can_manage_members(auth: AuthContext, db: AsyncSession) -> Optional[User]:
    """API key (sem user) ou usuário admin/coordinator podem gerenciar."""
    if not auth.user_id:
        return None
    user = await db.get(User, auth.user_id)
    if not user or not user.is_active or user.tenant_id != auth.tenant_id:
        raise HTTPException(status_code=403, detail="Sem permissão para gerenciar membros.")
    if user.role not in ("admin", "coordinator"):
        raise HTTPException(status_code=403, detail="Apenas administradores ou coordenação podem convidar.")
    return user


class InviteCreatePayload(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    role: Literal["admin", "coordinator", "operator", "viewer"] = "coordinator"

    @field_validator("email")
    @classmethod
    def email_ok(cls, value: str) -> str:
        return _normalize_email(value)


class AcceptInvitePayload(BaseModel):
    token: str = Field(min_length=16, max_length=512)
    password: str = Field(min_length=8, max_length=256)
    phone: str = Field(min_length=8, max_length=30)
    display_name: Optional[str] = Field(default=None, max_length=120)


def _member_dict(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role if user.role in _VALID_ROLES else "coordinator",
        "status": "active" if user.is_active else "disabled",
        "phone": user.phone_e164,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


def _invite_dict(inv: OrganizationInvite, invite_url: Optional[str] = None) -> dict:
    data = {
        "id": inv.id,
        "email": inv.email,
        "role": inv.role,
        "status": inv.status,
        "created_at": inv.created_at.isoformat() if inv.created_at else None,
        "expires_at": inv.expires_at.isoformat() if inv.expires_at else None,
    }
    if invite_url:
        data["invite_url"] = invite_url
    return data


@router.get("/members")
async def list_members(
    auth: AuthContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(User)
        .where(User.tenant_id == auth.tenant_id)
        .order_by(User.created_at.asc())
    )
    users = result.scalars().all()
    return {
        "organization_name": auth.tenant.name,
        "members": [_member_dict(u) for u in users],
    }


@router.get("/invites")
async def list_invites(
    auth: AuthContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    await _require_can_manage_members(auth, db)
    result = await db.execute(
        select(OrganizationInvite)
        .where(
            OrganizationInvite.tenant_id == auth.tenant_id,
            OrganizationInvite.status == "pending",
        )
        .order_by(OrganizationInvite.created_at.desc())
    )
    invites = result.scalars().all()
    # Expira visualmente os vencidos
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
    auth: AuthContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    inviter = await _require_can_manage_members(auth, db)
    settings = get_settings()

    existing_user = await db.execute(select(User.id).where(User.email == body.email))
    if existing_user.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Já existe uma conta com esse e-mail.")

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
        role=body.role,
        token_hash=_invite_token_hash(raw_token),
        status="pending",
        invited_by_user_id=inviter.id if inviter else None,
        expires_at=_now() + timedelta(days=_INVITE_TTL_DAYS),
    )
    db.add(invite)
    await db.commit()
    await db.refresh(invite)

    invite_url = f"{settings.mira_public_url.rstrip('/')}/convite/{raw_token}"

    # E-mail real só se Resend estiver configurado; em dev o link volta na resposta
    emailed = False
    if settings.resend_api_key and settings.email_from:
        body_text = (
            f"Você foi convidado(a) para a organização {auth.tenant.name} na Mira.\n\n"
            f"Perfil de acesso: {body.role}\n\n"
            f"Abra o link abaixo para criar sua senha e telefone (válido por {_INVITE_TTL_DAYS} dias):\n\n"
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
            else "Convite criado. Em desenvolvimento o link é devolvido na resposta (configure Resend para envio real)."
        ),
        "invite": _invite_dict(invite, invite_url=invite_url),
        "invite_url": invite_url,
    }


@router.post("/invites/accept")
async def accept_invite(
    body: AcceptInvitePayload,
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
    user = User(
        tenant_id=invite.tenant_id,
        display_name=display[:120],
        email=invite.email,
        phone_e164=phone,
        password_hash=hash_password(body.password),
        role=invite.role if invite.role in _VALID_ROLES else "coordinator",
        is_active=True,
    )
    db.add(user)
    invite.status = "accepted"
    invite.accepted_at = now
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Não foi possível ativar o acesso.")
    await db.refresh(user)

    token, ttl = issue_access_token(
        user_id=user.id, tenant_id=user.tenant_id, auth_version=user.auth_version
    )
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
