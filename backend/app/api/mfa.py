"""Endpoints MFA TOTP para contas institucionais da MIRA."""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthContext, get_current_tenant
from app.core.mira_security import issue_access_token
from app.core.mfa import (
    decrypt_totp_secret, encrypt_totp_secret, generate_recovery_codes,
    new_totp_secret, recovery_code_hash, totp_qr_data_uri, verify_totp,
)
from app.db.session import get_db
from app.models.auth import MfaAuditEvent, MfaLoginChallenge, MfaRecoveryCode, User
from app.models.tenant import Tenant

router = APIRouter(prefix="/auth/mfa", tags=["Autenticação multifator"])
TICKET_TTL_SECONDS = 300
MAX_ATTEMPTS = 5
LOCK_MINUTES = 15


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ticket_hash(ticket: str) -> str:
    return hashlib.sha256(("mira:mfa:login:" + ticket).encode()).hexdigest()


def _audit(db: AsyncSession, tenant_id: str, user_id: str | None, event: str, details: str | None = None):
    db.add(MfaAuditEvent(tenant_id=tenant_id, user_id=user_id, event_type=event, details=details))


def _require_user(auth: AuthContext) -> str:
    if not auth.user_id:
        raise HTTPException(status_code=401, detail="Esta operação exige uma sessão de usuário.")
    return auth.user_id


async def create_login_challenge(db: AsyncSession, user: User, tenant: Tenant) -> dict:
    ticket = secrets.token_urlsafe(32)
    db.add(MfaLoginChallenge(
        user_id=user.id, tenant_id=tenant.id, ticket_hash=_ticket_hash(ticket),
        expires_at=_now() + timedelta(seconds=TICKET_TTL_SECONDS),
    ))
    _audit(db, tenant.id, user.id, "login_challenge_created")
    await db.commit()
    return {"mfa_required": True, "challenge_token": ticket, "expires_in": TICKET_TTL_SECONDS}


class LoginMfaPayload(BaseModel):
    challenge_token: str = Field(min_length=32, max_length=128)
    code: str = Field(min_length=6, max_length=32)


class MfaCodePayload(BaseModel):
    code: str = Field(min_length=6, max_length=32)


@router.post("/login/verify")
async def verify_login_mfa(body: LoginMfaPayload, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(MfaLoginChallenge)
        .where(MfaLoginChallenge.ticket_hash == _ticket_hash(body.challenge_token))
        .with_for_update()
    )
    challenge = result.scalar_one_or_none()
    now = _now()
    if not challenge or challenge.consumed_at or challenge.expires_at <= now:
        raise HTTPException(status_code=401, detail="Desafio inválido ou expirado.")
    if challenge.attempts >= MAX_ATTEMPTS:
        raise HTTPException(status_code=429, detail="Limite de tentativas atingido. Inicie o login novamente.")
    challenge.attempts += 1
    user_result = await db.execute(
        select(User).where(User.id == challenge.user_id).with_for_update()
    )
    user = user_result.scalar_one_or_none()
    tenant = await db.get(Tenant, challenge.tenant_id)
    if not user or not tenant or not user.is_active or not tenant.is_active or not user.mfa_enabled_at or not user.mfa_totp_secret_encrypted:
        challenge.consumed_at = now
        await db.commit()
        raise HTTPException(status_code=401, detail="Desafio inválido ou expirado.")
    if user.mfa_locked_until and user.mfa_locked_until > now:
        await db.commit()
        raise HTTPException(status_code=429, detail="MFA temporariamente bloqueado. Tente novamente mais tarde.")

    accepted_step = None
    recovery = None
    if body.code.isdigit() and len(body.code) == 6:
        secret = decrypt_totp_secret(user.mfa_totp_secret_encrypted)
        accepted_step = verify_totp(secret, body.code, user.mfa_last_verified_step)
    else:
        digest = recovery_code_hash(body.code)
        row_result = await db.execute(
            select(MfaRecoveryCode).where(
                MfaRecoveryCode.user_id == user.id,
                MfaRecoveryCode.code_hash == digest,
                MfaRecoveryCode.used_at.is_(None),
            ).with_for_update()
        )
        recovery = row_result.scalar_one_or_none()

    if accepted_step is None and recovery is None:
        if challenge.attempts >= MAX_ATTEMPTS:
            challenge.consumed_at = now
        user.mfa_failed_attempts += 1
        if user.mfa_failed_attempts >= MAX_ATTEMPTS:
            user.mfa_locked_until = now + timedelta(minutes=LOCK_MINUTES)
            user.mfa_failed_attempts = 0
        _audit(db, tenant.id, user.id, "login_verification_failed")
        await db.commit()
        raise HTTPException(status_code=401, detail="Código inválido ou expirado.")

    if recovery:
        recovery.used_at = now
        _audit(db, tenant.id, user.id, "recovery_code_used")
    else:
        user.mfa_last_verified_step = accepted_step
    user.mfa_failed_attempts = 0
    user.mfa_locked_until = None
    challenge.consumed_at = now
    _audit(db, tenant.id, user.id, "login_verified")
    await db.commit()
    token, ttl = issue_access_token(user_id=user.id, tenant_id=user.tenant_id, auth_version=user.auth_version, aal=2)
    return {
        "access_token": token, "token_type": "bearer", "expires_in": ttl,
        "user": {"display_name": user.display_name, "email": user.email, "tenant_name": tenant.name},
    }


@router.get("/status")
async def mfa_status(
    auth: AuthContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    user_id = _require_user(auth)
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Sessão inválida.")
    count_result = await db.execute(
        select(MfaRecoveryCode.id).where(MfaRecoveryCode.user_id == user_id, MfaRecoveryCode.used_at.is_(None))
    )
    return {
        "enabled": bool(user.mfa_enabled_at),
        "enabled_at": user.mfa_enabled_at.isoformat() if user.mfa_enabled_at else None,
        "recovery_codes_remaining": len(count_result.scalars().all()),
    }


@router.post("/enroll")
async def enroll_mfa(
    auth: AuthContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    user_id = _require_user(auth)
    user = await db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Sessão inválida.")
    if user.mfa_enabled_at:
        raise HTTPException(status_code=409, detail="MFA já está ativo nesta conta.")
    secret = new_totp_secret()
    user.mfa_totp_secret_encrypted = encrypt_totp_secret(secret)
    user.mfa_last_verified_step = None
    _audit(db, auth.tenant_id, user.id, "enrollment_started")
    await db.commit()
    return {
        "secret": secret,
        "qr_code": totp_qr_data_uri(secret, user.email),
        "otpauth_uri": f"otpauth://totp/MIRA:{user.email}?secret={secret}&issuer=MIRA&algorithm=SHA1&digits=6&period=30",
    }


@router.post("/confirm")
async def confirm_mfa(
    body: MfaCodePayload,
    auth: AuthContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    user_id = _require_user(auth)
    user = await db.get(User, user_id)
    if not user or not user.mfa_totp_secret_encrypted or user.mfa_enabled_at:
        raise HTTPException(status_code=409, detail="Não existe uma configuração MFA pendente.")
    secret = decrypt_totp_secret(user.mfa_totp_secret_encrypted)
    step = verify_totp(secret, body.code)
    if step is None:
        _audit(db, auth.tenant_id, user.id, "enrollment_verification_failed")
        await db.commit()
        raise HTTPException(status_code=400, detail="Código inválido. Confira o aplicativo autenticador.")
    user.mfa_enabled_at = _now()
    user.mfa_last_verified_step = step
    user.auth_version += 1
    user.mfa_failed_attempts = 0
    user.mfa_locked_until = None
    codes = generate_recovery_codes()
    for code in codes:
        db.add(MfaRecoveryCode(user_id=user.id, code_hash=recovery_code_hash(code)))
    _audit(db, auth.tenant_id, user.id, "mfa_enabled")
    await db.commit()
    token, ttl = issue_access_token(user_id=user.id, tenant_id=user.tenant_id, auth_version=user.auth_version, aal=2)
    return {"enabled": True, "recovery_codes": codes, "access_token": token, "token_type": "bearer", "expires_in": ttl}


@router.post("/recovery-codes/regenerate")
async def regenerate_recovery_codes(
    body: MfaCodePayload,
    auth: AuthContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    user_id = _require_user(auth)
    user = await db.get(User, user_id)
    if not user or not user.mfa_enabled_at or not user.mfa_totp_secret_encrypted:
        raise HTTPException(status_code=409, detail="MFA não está ativo.")
    step = verify_totp(decrypt_totp_secret(user.mfa_totp_secret_encrypted), body.code, user.mfa_last_verified_step)
    if step is None:
        raise HTTPException(status_code=401, detail="Código inválido.")
    user.mfa_last_verified_step = step
    await db.execute(update(MfaRecoveryCode).where(MfaRecoveryCode.user_id == user_id, MfaRecoveryCode.used_at.is_(None)).values(used_at=_now()))
    codes = generate_recovery_codes()
    for code in codes:
        db.add(MfaRecoveryCode(user_id=user_id, code_hash=recovery_code_hash(code)))
    _audit(db, auth.tenant_id, user.id, "recovery_codes_regenerated")
    await db.commit()
    return {"recovery_codes": codes}


@router.post("/disable")
async def disable_mfa(
    body: MfaCodePayload,
    auth: AuthContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    user_id = _require_user(auth)
    user = await db.get(User, user_id)
    if not user or not user.mfa_enabled_at or not user.mfa_totp_secret_encrypted:
        raise HTTPException(status_code=409, detail="MFA não está ativo.")
    step = verify_totp(decrypt_totp_secret(user.mfa_totp_secret_encrypted), body.code, user.mfa_last_verified_step)
    if step is None:
        raise HTTPException(status_code=401, detail="Código inválido.")
    user.mfa_enabled_at = None
    user.mfa_totp_secret_encrypted = None
    user.mfa_last_verified_step = None
    user.auth_version += 1
    await db.execute(update(MfaRecoveryCode).where(MfaRecoveryCode.user_id == user_id, MfaRecoveryCode.used_at.is_(None)).values(used_at=_now()))
    _audit(db, auth.tenant_id, user.id, "mfa_disabled")
    await db.commit()
    token, ttl = issue_access_token(user_id=user.id, tenant_id=user.tenant_id, auth_version=user.auth_version, aal=1)
    return {"enabled": False, "access_token": token, "token_type": "bearer", "expires_in": ttl}
