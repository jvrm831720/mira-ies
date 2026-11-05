"""Autenticação de contas Mira: senha, código WhatsApp e redefinição por e-mail."""
from __future__ import annotations

import hmac
import logging
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.channels.whatsapp import normalize_phone_br
from app.agents.providers.whatsapp import send_whatsapp
from app.agents.providers.resend_provider import send_email_resend
from app.core.config import get_settings
from app.core.mira_security import hash_password, verify_password
from app.core.security import hash_api_key
from app.db.session import get_db
from app.models.auth import AuthChallenge, User, UserSession
from app.api.mfa import create_login_challenge
from app.core.mfa_policy import user_requires_mfa
from app.core.user_sessions import create_user_session
from app.models.tenant import Tenant
from app.services.membership import ensure_membership, get_membership_for_tenant

router = APIRouter(prefix="/auth", tags=["Autenticação Mira"])
logger = logging.getLogger(__name__)
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_ACCESS_DENIED = "E-mail, senha ou código inválido."
_LOGIN_COOLDOWN_SECONDS = 60
_OTP_TTL_MINUTES = 5
_RESET_TTL_MINUTES = 30
_MAX_CHALLENGE_ATTEMPTS = 5
_DUMMY_PASSWORD_HASH = hash_password(secrets.token_urlsafe(32))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _email(value: str) -> str:
    normalized = value.strip().lower()
    if not _EMAIL_RE.fullmatch(normalized):
        raise ValueError("Informe um e-mail válido.")
    return normalized


def _fingerprint(kind: str, identifier: str) -> str:
    return hash_api_key(f"mira:challenge:{kind}:{identifier}")


def _token_digest(kind: str, identifier: str, token: str) -> str:
    return hash_api_key(f"mira:token:{kind}:{identifier}:{token}")


def _reset_digest(token: str) -> str:
    return hash_api_key(f"mira:password-reset:{token}")


async def _token_response(user: User, tenant: Tenant, request: Request, db: AsyncSession) -> dict:
    token, ttl = await create_user_session(db, user, tenant, request, aal=1)
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": ttl,
        "user": {"display_name": user.display_name, "email": user.email, "tenant_name": tenant.name},
    }


async def _active_tenant(db: AsyncSession, user: User) -> Tenant | None:
    tenant = await db.get(Tenant, user.tenant_id)
    if not user.is_active or not tenant or not tenant.is_active:
        return None
    await db.execute(text("SELECT set_config('app.user_id', :user_id, true)"), {"user_id": user.id})
    await db.execute(text("SELECT set_config('app.tenant_id', :tenant_id, true)"), {"tenant_id": tenant.id})
    membership = await get_membership_for_tenant(
        db, user_id=user.id, tenant_id=tenant.id
    )
    if membership and membership.status != "active":
        return None
    return tenant


async def _check_cooldown(db: AsyncSession, kind: str, identifier_hash: str) -> None:
    cutoff = _now() - timedelta(seconds=_LOGIN_COOLDOWN_SECONDS)
    previous = await db.execute(
        select(AuthChallenge.id).where(
            AuthChallenge.challenge_type == kind,
            AuthChallenge.identifier_hash == identifier_hash,
            AuthChallenge.created_at >= cutoff,
        ).limit(1)
    )
    if previous.scalar_one_or_none():
        raise HTTPException(status_code=429, detail="Aguarde um minuto antes de solicitar outro código.")


class EmailPayload(BaseModel):
    email: str = Field(min_length=5, max_length=255)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return _email(value)


class PasswordLoginPayload(EmailPayload):
    password: str = Field(min_length=1, max_length=256)


class WhatsAppRequestPayload(BaseModel):
    phone: str = Field(min_length=8, max_length=30)


class WhatsAppVerifyPayload(WhatsAppRequestPayload):
    code: str = Field(pattern=r"^\d{6}$")


class PasswordResetPayload(BaseModel):
    token: str = Field(min_length=20, max_length=512)
    new_password: str = Field(min_length=12, max_length=256)


class ProvisionUserPayload(EmailPayload):
    tenant_slug: str = Field(min_length=2, max_length=80, pattern=r"^[a-z0-9][a-z0-9-]*$")
    display_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=12, max_length=256)
    phone: Optional[str] = Field(default=None, min_length=8, max_length=30)


@router.post("/login/password")
async def login_password(body: PasswordLoginPayload, request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    now = _now()
    if user and user.locked_until and user.locked_until > now:
        raise HTTPException(status_code=429, detail="Acesso temporariamente bloqueado. Tente novamente mais tarde.")
    password_valid = verify_password(body.password, user.password_hash if user else _DUMMY_PASSWORD_HASH)
    if not user or not password_valid:
        if user:
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= 10:
                user.failed_login_attempts = 0
                user.locked_until = now + timedelta(minutes=15)
            await db.commit()
        raise HTTPException(status_code=401, detail=_ACCESS_DENIED)
    tenant = await _active_tenant(db, user)
    if tenant is None:
        raise HTTPException(status_code=401, detail=_ACCESS_DENIED)
    user.failed_login_attempts = 0
    user.locked_until = None
    if await user_requires_mfa(db, user):
        return await create_login_challenge(
            db, user, tenant, purpose="verify" if user.mfa_enabled_at else "enroll"
        )
    response = await _token_response(user, tenant, request, db)
    await db.commit()
    return response


class EmailOtpVerifyPayload(EmailPayload):
    code: str = Field(pattern=r"^\d{6}$")


@router.post("/email/request", status_code=status.HTTP_202_ACCEPTED)
async def request_email_login_code(body: EmailPayload, db: AsyncSession = Depends(get_db)):
    """Envia OTP para qualquer e-mail; a existência da conta só é revelada após validar o código."""
    settings = get_settings()
    if not settings.resend_api_key or not settings.email_from:
        raise HTTPException(status_code=503, detail="Login por e-mail temporariamente indisponível.")

    identifier_hash = _fingerprint("email_login", body.email)
    await _check_cooldown(db, "email_login", identifier_hash)
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    code = f"{secrets.randbelow(1_000_000):06d}"
    challenge = AuthChallenge(
        user_id=user.id if user else None,
        challenge_type="email_login",
        identifier_hash=identifier_hash,
        token_hash=_token_digest("email_login", body.email, code),
        expires_at=_now() + timedelta(minutes=_OTP_TTL_MINUTES),
    )
    await db.execute(
        update(AuthChallenge)
        .where(
            AuthChallenge.challenge_type == "email_login",
            AuthChallenge.identifier_hash == identifier_hash,
            AuthChallenge.consumed_at.is_(None),
        )
        .values(consumed_at=_now())
    )
    db.add(challenge)
    await db.commit()

    greeting = f"Olá, {user.display_name}." if user else "Olá."
    delivery = await send_email_resend(
        to=body.email,
        subject="Seu código de acesso à MIRA",
        body=(
            f"{greeting}\n\n"
            f"Seu código de acesso à MIRA é {code}.\n"
            f"Ele expira em {_OTP_TTL_MINUTES} minutos e só pode ser usado uma vez. "
            "Não compartilhe este código.\n\n"
            "Se você não solicitou este acesso, ignore esta mensagem."
        ),
    )
    if not delivery.ok:
        logger.warning("Falha na entrega de código de acesso MIRA via Resend.")
    return {"message": "Se houver uma conta ou possibilidade de cadastro para este e-mail, enviaremos um código."}


@router.post("/email/verify")
async def verify_email_login_code(
    body: EmailOtpVerifyPayload,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    identifier_hash = _fingerprint("email_login", body.email)
    result = await db.execute(
        select(AuthChallenge)
        .where(
            AuthChallenge.challenge_type == "email_login",
            AuthChallenge.identifier_hash == identifier_hash,
            AuthChallenge.consumed_at.is_(None),
        )
        .order_by(AuthChallenge.created_at.desc())
        .limit(1)
        .with_for_update()
    )
    challenge = result.scalar_one_or_none()
    now = _now()
    if not challenge or challenge.expires_at <= now:
        raise HTTPException(status_code=401, detail=_ACCESS_DENIED)
    if challenge.attempts >= _MAX_CHALLENGE_ATTEMPTS:
        raise HTTPException(status_code=429, detail="Limite de tentativas atingido. Solicite um novo código.")

    challenge.attempts += 1
    expected = _token_digest("email_login", body.email, body.code)
    if not hmac.compare_digest(challenge.token_hash, expected):
        if challenge.attempts >= _MAX_CHALLENGE_ATTEMPTS:
            challenge.consumed_at = now
        await db.commit()
        raise HTTPException(status_code=401, detail=_ACCESS_DENIED)

    challenge.consumed_at = now
    if challenge.user_id is None:
        onboarding_token = secrets.token_urlsafe(32)
        db.add(AuthChallenge(
            user_id=None,
            challenge_type="onboarding_provision",
            identifier_hash=_fingerprint("onboarding", body.email),
            token_hash=_token_digest("onboarding", body.email, onboarding_token),
            expires_at=now + timedelta(minutes=30),
        ))
        await db.commit()
        return {
            "onboarding_required": True,
            "email": body.email,
            "onboarding_token": onboarding_token,
        }

    user = await db.get(User, challenge.user_id)
    tenant = await _active_tenant(db, user) if user else None
    if tenant is None or (user.locked_until and user.locked_until > now):
        await db.commit()
        raise HTTPException(status_code=401, detail=_ACCESS_DENIED)
    if await user_requires_mfa(db, user):
        return await create_login_challenge(
            db, user, tenant, purpose="verify" if user.mfa_enabled_at else "enroll"
        )
    response = await _token_response(user, tenant, request, db)
    await db.commit()
    return response


@router.post("/whatsapp/request", status_code=status.HTTP_202_ACCEPTED)
async def request_whatsapp_code(body: WhatsAppRequestPayload, db: AsyncSession = Depends(get_db)):
    settings = get_settings()
    waha_configured = bool(settings.waha_api_url and settings.waha_api_key)
    evolution_configured = bool(settings.evolution_api_url and settings.evolution_api_key)
    if not (waha_configured or evolution_configured):
        raise HTTPException(status_code=503, detail="Login por WhatsApp indisponível: configure um provider WhatsApp.")
    phone = normalize_phone_br(body.phone)
    if not phone:
        raise HTTPException(status_code=422, detail="Informe um número de telefone válido com DDD.")
    identifier_hash = _fingerprint("whatsapp", phone)
    await _check_cooldown(db, "whatsapp_login", identifier_hash)

    result = await db.execute(select(User).where(User.phone_e164 == phone))
    user = result.scalar_one_or_none()
    tenant = await _active_tenant(db, user) if user else None
    code = f"{secrets.randbelow(1_000_000):06d}"
    challenge = AuthChallenge(
        user_id=user.id if tenant else None,
        challenge_type="whatsapp_login",
        identifier_hash=identifier_hash,
        token_hash=_token_digest("whatsapp", phone, code),
        expires_at=_now() + timedelta(minutes=_OTP_TTL_MINUTES),
    )
    await db.execute(
        update(AuthChallenge)
        .where(
            AuthChallenge.challenge_type == "whatsapp_login",
            AuthChallenge.identifier_hash == identifier_hash,
            AuthChallenge.consumed_at.is_(None),
        )
        .values(consumed_at=_now())
    )
    db.add(challenge)
    await db.commit()

    if tenant:
        delivery = await send_whatsapp(
            to=phone,
            message=f"Seu código de acesso Mira é {code}. Ele expira em 5 minutos. Não compartilhe este código.",
        )
        if not delivery.ok:
            logger.warning("Falha na entrega de código de acesso Mira via provider WhatsApp.")
    return {"message": "Se o número estiver cadastrado, enviaremos um código pelo WhatsApp."}


@router.post("/whatsapp/verify")
async def verify_whatsapp_code(body: WhatsAppVerifyPayload, request: Request, db: AsyncSession = Depends(get_db)):
    phone = normalize_phone_br(body.phone)
    if not phone:
        raise HTTPException(status_code=401, detail=_ACCESS_DENIED)
    identifier_hash = _fingerprint("whatsapp", phone)
    result = await db.execute(
        select(AuthChallenge)
        .where(
            AuthChallenge.challenge_type == "whatsapp_login",
            AuthChallenge.identifier_hash == identifier_hash,
            AuthChallenge.consumed_at.is_(None),
        )
        .order_by(AuthChallenge.created_at.desc())
        .limit(1)
        .with_for_update()
    )
    challenge = result.scalar_one_or_none()
    now = _now()
    if not challenge or not challenge.user_id or challenge.expires_at <= now:
        raise HTTPException(status_code=401, detail=_ACCESS_DENIED)
    if challenge.attempts >= _MAX_CHALLENGE_ATTEMPTS:
        raise HTTPException(status_code=429, detail="Limite de tentativas atingido. Solicite um novo código.")
    challenge.attempts += 1
    expected = _token_digest("whatsapp", phone, body.code)
    if not hmac.compare_digest(challenge.token_hash, expected):
        if challenge.attempts >= _MAX_CHALLENGE_ATTEMPTS:
            challenge.consumed_at = now
        await db.commit()
        raise HTTPException(status_code=401, detail=_ACCESS_DENIED)
    challenge.consumed_at = now
    user = await db.get(User, challenge.user_id)
    tenant = await _active_tenant(db, user) if user else None
    if tenant is None:
        await db.commit()
        raise HTTPException(status_code=401, detail=_ACCESS_DENIED)
    if await user_requires_mfa(db, user):
        return await create_login_challenge(
            db, user, tenant, purpose="verify" if user.mfa_enabled_at else "enroll"
        )
    response = await _token_response(user, tenant, request, db)
    await db.commit()
    return response


@router.post("/password/forgot", status_code=status.HTTP_202_ACCEPTED)
async def forgot_password(body: EmailPayload, db: AsyncSession = Depends(get_db)):
    settings = get_settings()
    if not settings.resend_api_key or not settings.email_from:
        raise HTTPException(status_code=503, detail="Recuperação por e-mail indisponível: configure Resend e EMAIL_FROM.")
    identifier_hash = _fingerprint("password_reset", body.email)
    await _check_cooldown(db, "password_reset", identifier_hash)
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    tenant = await _active_tenant(db, user) if user else None
    token = secrets.token_urlsafe(32)
    challenge = AuthChallenge(
        user_id=user.id if tenant else None,
        challenge_type="password_reset",
        identifier_hash=identifier_hash,
        token_hash=_reset_digest(token),
        expires_at=_now() + timedelta(minutes=_RESET_TTL_MINUTES),
    )
    await db.execute(
        update(AuthChallenge)
        .where(
            AuthChallenge.challenge_type == "password_reset",
            AuthChallenge.identifier_hash == identifier_hash,
            AuthChallenge.consumed_at.is_(None),
        )
        .values(consumed_at=_now())
    )
    db.add(challenge)
    await db.commit()

    if tenant:
        link = f"{settings.mira_public_url.rstrip('/')}/reset-password?token={token}"
        delivery = await send_email_resend(
            to=user.email,
            subject="Redefinição de senha da Mira",
            body=(
                f"Olá, {user.display_name}.\n\n"
                f"Use o link abaixo para redefinir sua senha. Ele expira em {_RESET_TTL_MINUTES} minutos e só pode ser usado uma vez.\n\n"
                f"{link}\n\nSe você não solicitou esta alteração, ignore este e-mail."
            ),
        )
        if not delivery.ok:
            logger.warning("Falha na entrega de redefinição de senha via Resend.")
    return {"message": "Se o e-mail estiver cadastrado, enviaremos as instruções de redefinição."}


@router.post("/password/reset")
async def reset_password(body: PasswordResetPayload, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(AuthChallenge)
        .where(
            AuthChallenge.challenge_type == "password_reset",
            AuthChallenge.token_hash == _reset_digest(body.token),
            AuthChallenge.consumed_at.is_(None),
        )
        .limit(1)
        .with_for_update()
    )
    challenge = result.scalar_one_or_none()
    now = _now()
    if not challenge or not challenge.user_id or challenge.expires_at <= now:
        raise HTTPException(status_code=400, detail="Link de redefinição inválido ou expirado.")
    user = await db.get(User, challenge.user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=400, detail="Link de redefinição inválido ou expirado.")
    challenge.consumed_at = now
    user.password_hash = hash_password(body.new_password)
    user.auth_version += 1
    await db.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": user.tenant_id},
    )
    await db.execute(
        update(UserSession)
        .where(
            UserSession.tenant_id == user.tenant_id,
            UserSession.user_id == user.id,
            UserSession.revoked_at.is_(None),
        )
        .values(
            revoked_at=now,
            revoked_by_user_id=user.id,
            revoke_reason="password_reset",
        )
    )
    user.failed_login_attempts = 0
    user.locked_until = None
    await db.execute(
        update(AuthChallenge)
        .where(AuthChallenge.user_id == user.id, AuthChallenge.consumed_at.is_(None))
        .values(consumed_at=now)
    )
    await db.commit()
    return {"message": "Senha redefinida. Você já pode entrar com a nova senha."}


@router.post("/admin/users", status_code=status.HTTP_201_CREATED)
async def provision_user(
    body: ProvisionUserPayload,
    db: AsyncSession = Depends(get_db),
    x_admin_secret: Optional[str] = Header(default=None, alias="X-Admin-Secret"),
):
    settings = get_settings()
    if settings.app_env != "development":
        admin_secret = settings.mira_admin_secret or settings.secret_key
        if not x_admin_secret or not hmac.compare_digest(x_admin_secret, admin_secret):
            raise HTTPException(status_code=403, detail="X-Admin-Secret inválido.")
    tenant_result = await db.execute(select(Tenant).where(Tenant.slug == body.tenant_slug))
    tenant = tenant_result.scalar_one_or_none()
    if not tenant or not tenant.is_active:
        raise HTTPException(status_code=404, detail="Instituição não encontrada ou inativa.")
    existing = await db.execute(select(User.id).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Já existe uma conta com esse e-mail.")
    phone = normalize_phone_br(body.phone) if body.phone else None
    if body.phone and not phone:
        raise HTTPException(status_code=422, detail="Informe um telefone válido com DDD.")
    user = User(
        tenant_id=tenant.id,
        display_name=body.display_name.strip(),
        email=body.email,
        phone_e164=phone,
        password_hash=hash_password(body.password),
        role="admin",
        is_active=True,
    )
    db.add(user)
    await db.flush()
    await db.execute(text("SELECT set_config('app.user_id', :user_id, true)"), {"user_id": user.id})
    await db.execute(text("SELECT set_config('app.tenant_id', :tenant_id, true)"), {"tenant_id": tenant.id})
    await ensure_membership(
        db,
        user=user,
        tenant_id=tenant.id,
        role=user.role or "admin",
        origin="provision",
        status="active",
    )
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Não foi possível criar a conta; verifique e-mail e telefone.")
    await db.refresh(user)
    return {"id": user.id, "email": user.email, "display_name": user.display_name, "tenant": tenant.slug}
