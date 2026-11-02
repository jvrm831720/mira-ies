"""MFA TOTP, políticas institucionais e sessões revogáveis."""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthContext, get_current_tenant
from app.core.mfa import (
    decrypt_totp_secret,
    encrypt_totp_secret,
    generate_recovery_codes,
    new_totp_secret,
    recovery_code_hash,
    totp_qr_data_uri,
    verify_totp,
)
from app.core.mfa_policy import VALID_MFA_ROLES, get_tenant_mfa_policy, user_requires_mfa
from app.core.user_sessions import create_user_session
from app.db.session import get_db
from app.models.auth import (
    MfaAuditEvent,
    MfaLoginChallenge,
    MfaRecoveryCode,
    MfaTenantPolicy,
    User,
    UserSession,
)
from app.models.tenant import Tenant

router = APIRouter(prefix="/auth/mfa", tags=["Autenticação multifator"])
TICKET_TTL_SECONDS = 300
MAX_ATTEMPTS = 5
LOCK_MINUTES = 15
RECENT_AUTH_SECONDS = 600


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ticket_hash(ticket: str) -> str:
    return hashlib.sha256(("mira:mfa:login:" + ticket).encode()).hexdigest()


def _audit(db: AsyncSession, tenant_id: str, user_id: str | None, event: str, details: str | None = None) -> None:
    db.add(MfaAuditEvent(tenant_id=tenant_id, user_id=user_id, event_type=event, details=details))


def _require_user(auth: AuthContext) -> str:
    if not auth.user_id or not auth.session_id:
        raise HTTPException(status_code=401, detail="Esta operação exige uma sessão de usuário.")
    return auth.user_id


def _require_recent_auth(auth: AuthContext, *, minimum_aal: int = 1) -> None:
    now = int(_now().timestamp())
    if auth.aal < minimum_aal or not auth.authenticated_at or now - auth.authenticated_at > RECENT_AUTH_SECONDS:
        raise HTTPException(
            status_code=403,
            detail="Confirme sua identidade novamente antes desta operação.",
        )


def _require_admin(auth: AuthContext) -> str:
    user_id = _require_user(auth)
    if auth.role != "admin":
        raise HTTPException(status_code=403, detail="Apenas administradores da instituição podem alterar esta política.")
    _require_recent_auth(auth, minimum_aal=2)
    return user_id


async def create_login_challenge(
    db: AsyncSession,
    user: User,
    tenant: Tenant,
    *,
    purpose: str = "verify",
) -> dict:
    if purpose not in {"verify", "enroll"}:
        raise ValueError("Finalidade de desafio MFA inválida.")
    ticket = secrets.token_urlsafe(32)
    db.add(MfaLoginChallenge(
        user_id=user.id,
        tenant_id=tenant.id,
        ticket_hash=_ticket_hash(ticket),
        purpose=purpose,
        expires_at=_now() + timedelta(seconds=TICKET_TTL_SECONDS),
    ))
    _audit(db, tenant.id, user.id, "login_challenge_created", purpose)
    await db.commit()
    return {
        "mfa_required": purpose == "verify",
        "mfa_enrollment_required": purpose == "enroll",
        "challenge_token": ticket,
        "expires_in": TICKET_TTL_SECONDS,
    }


class LoginMfaPayload(BaseModel):
    challenge_token: str = Field(min_length=32, max_length=128)
    code: str = Field(min_length=6, max_length=32)


class MfaCodePayload(BaseModel):
    code: str = Field(min_length=6, max_length=32)


class MfaPolicyPayload(BaseModel):
    require_mfa_all: bool = False
    required_roles: list[str] = Field(default_factory=list)

    @field_validator("required_roles")
    @classmethod
    def valid_roles(cls, roles: list[str]) -> list[str]:
        normalized = sorted(set(roles))
        if any(role not in VALID_MFA_ROLES for role in normalized):
            raise ValueError("Perfil inválido na política MFA.")
        return normalized


async def _load_challenge(db: AsyncSession, token: str, expected_purpose: str) -> MfaLoginChallenge:
    result = await db.execute(
        select(MfaLoginChallenge)
        .where(MfaLoginChallenge.ticket_hash == _ticket_hash(token))
        .with_for_update()
    )
    challenge = result.scalar_one_or_none()
    now = _now()
    if (
        not challenge
        or challenge.consumed_at is not None
        or challenge.expires_at <= now
        or challenge.purpose != expected_purpose
    ):
        raise HTTPException(status_code=401, detail="Desafio inválido ou expirado.")
    if challenge.attempts >= MAX_ATTEMPTS:
        raise HTTPException(status_code=429, detail="Limite de tentativas atingido. Inicie o login novamente.")
    return challenge


async def _load_challenge_identity(db: AsyncSession, challenge: MfaLoginChallenge) -> tuple[User, Tenant]:
    user_result = await db.execute(select(User).where(User.id == challenge.user_id).with_for_update())
    user = user_result.scalar_one_or_none()
    tenant = await db.get(Tenant, challenge.tenant_id)
    if not user or not tenant or user.tenant_id != tenant.id or not user.is_active or not tenant.is_active:
        challenge.consumed_at = _now()
        await db.commit()
        raise HTTPException(status_code=401, detail="Desafio inválido ou expirado.")
    return user, tenant


def _auth_response(db: AsyncSession, user: User, tenant: Tenant, request: Request, *, aal: int) -> dict:
    token, ttl = create_user_session(db, user, tenant, request, aal=aal)
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": ttl,
        "user": {"display_name": user.display_name, "email": user.email, "tenant_name": tenant.name},
    }


@router.post("/login/verify")
async def verify_login_mfa(
    body: LoginMfaPayload,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    challenge = await _load_challenge(db, body.challenge_token, "verify")
    challenge.attempts += 1
    user, tenant = await _load_challenge_identity(db, challenge)
    if not user.mfa_enabled_at or not user.mfa_totp_secret_encrypted:
        challenge.consumed_at = _now()
        await db.commit()
        raise HTTPException(status_code=401, detail="Desafio inválido ou expirado.")
    if user.mfa_locked_until and user.mfa_locked_until > _now():
        await db.commit()
        raise HTTPException(status_code=429, detail="MFA temporariamente bloqueado. Tente novamente mais tarde.")

    accepted_step = None
    recovery = None
    if body.code.isdigit() and len(body.code) == 6:
        accepted_step = verify_totp(
            decrypt_totp_secret(user.mfa_totp_secret_encrypted),
            body.code,
            user.mfa_last_verified_step,
        )
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
            challenge.consumed_at = _now()
        user.mfa_failed_attempts += 1
        if user.mfa_failed_attempts >= MAX_ATTEMPTS:
            user.mfa_locked_until = _now() + timedelta(minutes=LOCK_MINUTES)
            user.mfa_failed_attempts = 0
        _audit(db, tenant.id, user.id, "login_verification_failed")
        await db.commit()
        raise HTTPException(status_code=401, detail="Código inválido ou expirado.")

    if recovery:
        recovery.used_at = _now()
        _audit(db, tenant.id, user.id, "recovery_code_used")
    else:
        user.mfa_last_verified_step = accepted_step
    user.mfa_failed_attempts = 0
    user.mfa_locked_until = None
    challenge.consumed_at = _now()
    _audit(db, tenant.id, user.id, "login_verified")
    response = _auth_response(db, user, tenant, request, aal=2)
    await db.commit()
    return response


@router.post("/login/enroll")
async def begin_required_mfa_enrollment(
    body: MfaCodePayload,
    db: AsyncSession = Depends(get_db),
):
    challenge = await _load_challenge(db, body.code, "enroll")
    user, tenant = await _load_challenge_identity(db, challenge)
    if not await user_requires_mfa(db, user) or user.mfa_enabled_at:
        challenge.consumed_at = _now()
        await db.commit()
        raise HTTPException(status_code=409, detail="Este desafio não permite cadastro de MFA.")
    challenge.attempts += 1
    secret = new_totp_secret()
    user.mfa_totp_secret_encrypted = encrypt_totp_secret(secret)
    user.mfa_last_verified_step = None
    _audit(db, tenant.id, user.id, "required_enrollment_started")
    await db.commit()
    return {
        "secret": secret,
        "qr_code": totp_qr_data_uri(secret, user.email),
        "otpauth_uri": f"otpauth://totp/MIRA:{user.email}?secret={secret}&issuer=MIRA&algorithm=SHA1&digits=6&period=30",
    }


@router.post("/login/enroll/confirm")
async def confirm_required_mfa_enrollment(
    body: LoginMfaPayload,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    challenge = await _load_challenge(db, body.challenge_token, "enroll")
    challenge.attempts += 1
    user, tenant = await _load_challenge_identity(db, challenge)
    if user.mfa_enabled_at or not user.mfa_totp_secret_encrypted:
        raise HTTPException(status_code=409, detail="Não existe uma configuração MFA pendente.")
    if not await user_requires_mfa(db, user):
        raise HTTPException(status_code=409, detail="A política MFA não exige mais este cadastro.")
    step = verify_totp(decrypt_totp_secret(user.mfa_totp_secret_encrypted), body.code)
    if step is None:
        if challenge.attempts >= MAX_ATTEMPTS:
            challenge.consumed_at = _now()
        _audit(db, tenant.id, user.id, "required_enrollment_verification_failed")
        await db.commit()
        raise HTTPException(status_code=400, detail="Código inválido. Confira o aplicativo autenticador.")
    user.mfa_enabled_at = _now()
    user.mfa_last_verified_step = step
    user.mfa_failed_attempts = 0
    user.mfa_locked_until = None
    user.auth_version += 1
    codes = generate_recovery_codes()
    for code in codes:
        db.add(MfaRecoveryCode(user_id=user.id, code_hash=recovery_code_hash(code)))
    challenge.consumed_at = _now()
    _audit(db, tenant.id, user.id, "mfa_enabled_by_policy")
    response = _auth_response(db, user, tenant, request, aal=2)
    response["recovery_codes"] = codes
    response["enabled"] = True
    await db.commit()
    return response


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
        select(MfaRecoveryCode.id).where(
            MfaRecoveryCode.user_id == user_id,
            MfaRecoveryCode.used_at.is_(None),
        )
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
    _require_recent_auth(auth)
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
    request: Request,
    auth: AuthContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    user_id = _require_user(auth)
    _require_recent_auth(auth)
    user = await db.get(User, user_id)
    if not user or not user.mfa_totp_secret_encrypted or user.mfa_enabled_at:
        raise HTTPException(status_code=409, detail="Não existe uma configuração MFA pendente.")
    step = verify_totp(decrypt_totp_secret(user.mfa_totp_secret_encrypted), body.code)
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
    token, ttl = create_user_session(db, user, auth.tenant, request, aal=2)
    await db.commit()
    return {"enabled": True, "recovery_codes": codes, "access_token": token, "token_type": "bearer", "expires_in": ttl}


@router.post("/step-up")
async def step_up_mfa(
    body: MfaCodePayload,
    request: Request,
    auth: AuthContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    user_id = _require_user(auth)
    user = await db.get(User, user_id)
    if not user or not user.mfa_enabled_at or not user.mfa_totp_secret_encrypted:
        raise HTTPException(status_code=409, detail="Ative o MFA antes de confirmar novamente sua identidade.")
    step = verify_totp(decrypt_totp_secret(user.mfa_totp_secret_encrypted), body.code, user.mfa_last_verified_step)
    if step is None:
        _audit(db, auth.tenant_id, user.id, "step_up_failed")
        await db.commit()
        raise HTTPException(status_code=401, detail="Código inválido.")
    user.mfa_last_verified_step = step
    _audit(db, auth.tenant_id, user.id, "step_up_succeeded")
    token, ttl = create_user_session(db, user, auth.tenant, request, aal=2)
    await db.commit()
    return {"access_token": token, "token_type": "bearer", "expires_in": ttl}


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
    await db.execute(
        update(MfaRecoveryCode)
        .where(MfaRecoveryCode.user_id == user_id, MfaRecoveryCode.used_at.is_(None))
        .values(used_at=_now())
    )
    codes = generate_recovery_codes()
    for code in codes:
        db.add(MfaRecoveryCode(user_id=user_id, code_hash=recovery_code_hash(code)))
    _audit(db, auth.tenant_id, user.id, "recovery_codes_regenerated")
    await db.commit()
    return {"recovery_codes": codes}


@router.post("/disable")
async def disable_mfa(
    body: MfaCodePayload,
    request: Request,
    auth: AuthContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    user_id = _require_user(auth)
    user = await db.get(User, user_id)
    if not user or not user.mfa_enabled_at or not user.mfa_totp_secret_encrypted:
        raise HTTPException(status_code=409, detail="MFA não está ativo.")
    if await user_requires_mfa(db, user):
        policy = await get_tenant_mfa_policy(db, auth.tenant_id)
        if policy["require_mfa_all"] or user.role in policy["required_roles"]:
            raise HTTPException(status_code=409, detail="A política da instituição exige MFA para esta conta.")
    step = verify_totp(decrypt_totp_secret(user.mfa_totp_secret_encrypted), body.code, user.mfa_last_verified_step)
    if step is None:
        raise HTTPException(status_code=401, detail="Código inválido.")
    user.mfa_enabled_at = None
    user.mfa_totp_secret_encrypted = None
    user.mfa_last_verified_step = None
    user.auth_version += 1
    await db.execute(
        update(MfaRecoveryCode)
        .where(MfaRecoveryCode.user_id == user_id, MfaRecoveryCode.used_at.is_(None))
        .values(used_at=_now())
    )
    _audit(db, auth.tenant_id, user.id, "mfa_disabled")
    token, ttl = create_user_session(db, user, auth.tenant, request, aal=1)
    await db.commit()
    return {"enabled": False, "access_token": token, "token_type": "bearer", "expires_in": ttl}


@router.get("/policy")
async def read_mfa_policy(
    auth: AuthContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(auth)
    return await get_tenant_mfa_policy(db, auth.tenant_id)


@router.put("/policy")
async def update_mfa_policy(
    body: MfaPolicyPayload,
    request: Request,
    auth: AuthContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    user_id = _require_admin(auth)
    policy = await db.get(MfaTenantPolicy, auth.tenant_id)
    if policy is None:
        policy = MfaTenantPolicy(tenant_id=auth.tenant_id)
        db.add(policy)
    policy.require_mfa_all = body.require_mfa_all
    policy.required_roles = body.required_roles
    policy.updated_by_user_id = user_id
    policy.updated_at = _now()

    users_result = await db.execute(
        select(User).where(User.tenant_id == auth.tenant_id, User.is_active.is_(True)).with_for_update()
    )
    users = users_result.scalars().all()
    for member in users:
        member.auth_version += 1
    await db.execute(
        update(UserSession)
        .where(UserSession.tenant_id == auth.tenant_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=_now(), revoke_reason="institution_policy_changed")
    )
    _audit(
        db,
        auth.tenant_id,
        user_id,
        "mfa_policy_updated",
        f"require_all={body.require_mfa_all};required_roles={','.join(body.required_roles)}",
    )
    response = await get_tenant_mfa_policy(db, auth.tenant_id)
    token, ttl = create_user_session(db, await db.get(User, user_id), auth.tenant, request, aal=2)
    response.update({"access_token": token, "token_type": "bearer", "expires_in": ttl})
    await db.commit()
    return response


@router.get("/sessions")
async def list_user_sessions(
    auth: AuthContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    user_id = _require_user(auth)
    result = await db.execute(
        select(UserSession)
        .where(UserSession.tenant_id == auth.tenant_id, UserSession.user_id == user_id)
        .order_by(UserSession.created_at.desc())
        .limit(50)
    )
    sessions = result.scalars().all()
    return {
        "sessions": [
            {
                "id": session.id,
                "device_label": session.device_label,
                "user_agent": session.user_agent,
                "ip_address": session.ip_address,
                "aal": session.aal,
                "created_at": session.created_at.isoformat(),
                "expires_at": session.expires_at.isoformat(),
                "revoked_at": session.revoked_at.isoformat() if session.revoked_at else None,
                "current": session.id == auth.session_id,
                "active": session.revoked_at is None and session.expires_at > _now(),
            }
            for session in sessions
        ]
    }


@router.delete("/sessions/{session_id}")
async def revoke_user_session(
    session_id: str,
    auth: AuthContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    user_id = _require_user(auth)
    try:
        UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Sessão não encontrada.")
    session = await db.get(UserSession, session_id)
    if not session or session.tenant_id != auth.tenant_id or session.user_id != user_id:
        raise HTTPException(status_code=404, detail="Sessão não encontrada.")
    if session.id == auth.session_id:
        raise HTTPException(status_code=409, detail="Use o botão de sair para encerrar a sessão atual.")
    if session.revoked_at is None:
        session.revoked_at = _now()
        session.revoked_by_user_id = user_id
        session.revoke_reason = "revoked_by_owner"
        _audit(db, auth.tenant_id, user_id, "session_revoked", session.id)
        await db.commit()
    return {"revoked": True, "session_id": session.id}


@router.post("/sessions/revoke-others")
async def revoke_other_sessions(
    auth: AuthContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    user_id = _require_user(auth)
    result = await db.execute(
        update(UserSession)
        .where(
            UserSession.tenant_id == auth.tenant_id,
            UserSession.user_id == user_id,
            UserSession.id != auth.session_id,
            UserSession.revoked_at.is_(None),
        )
        .values(revoked_at=_now(), revoked_by_user_id=user_id, revoke_reason="revoked_other_sessions")
    )
    _audit(db, auth.tenant_id, user_id, "other_sessions_revoked", str(result.rowcount or 0))
    await db.commit()
    return {"revoked_count": result.rowcount or 0}


@router.post("/admin/users/{target_user_id}/revoke-sessions")
async def admin_revoke_user_sessions(
    target_user_id: str,
    auth: AuthContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    actor_id = _require_admin(auth)
    target = await db.get(User, target_user_id)
    if not target or target.tenant_id != auth.tenant_id:
        raise HTTPException(status_code=404, detail="Usuário não encontrado nesta instituição.")
    result = await db.execute(
        update(UserSession)
        .where(
            UserSession.tenant_id == auth.tenant_id,
            UserSession.user_id == target_user_id,
            UserSession.revoked_at.is_(None),
        )
        .values(
            revoked_at=_now(),
            revoked_by_user_id=actor_id,
            revoke_reason="revoked_by_institution_admin",
        )
    )
    target.auth_version += 1
    _audit(db, auth.tenant_id, actor_id, "member_sessions_revoked", target_user_id)
    await db.commit()
    return {"revoked_count": result.rowcount or 0, "user_id": target_user_id}
