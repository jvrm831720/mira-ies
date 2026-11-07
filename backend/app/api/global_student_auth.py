"""Global student portal identity, independent of every institution workspace.

Email OTP proves control of an inbox, NOT ownership of a CPF. The signed
identity-provider attestation is a separate, explicitly disabled production gate.
No endpoint in this module can query student, creditor or financial records.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import redis.asyncio as redis
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.providers.resend_provider import send_email_resend
from app.core.access_email_template import access_code_email
from app.core.config import get_settings
from app.db.session import get_db
from app.models.global_student_identity import (
    GlobalStudentAccount, GlobalStudentAttestation,
    GlobalStudentChallenge, GlobalStudentSession,
)

router = APIRouter(prefix="/global-portal", tags=["Portal MIRA — identidade global"])
_COOKIE = "mira_global_student_session"
_OTP_TTL = timedelta(minutes=5)
_SESSION_TTL = timedelta(hours=8)
_GENERIC = {"message": "Se os dados estiverem corretos, enviaremos um código para o e-mail cadastrado."}
_INVALID = "Código inválido ou expirado."
_EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_PHONE = re.compile(r"^55[1-9][0-9]{9,10}$")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _configured() -> str:
    settings = get_settings()
    secret = settings.global_student_identity_secret
    if (not settings.global_student_portal_enabled or not secret
            or len(secret) < 32 or not settings.resend_api_key or not settings.email_from):
        raise HTTPException(503, "Identidade global indisponível neste ambiente.")
    return secret


def _action(request: Request) -> None:
    if request.headers.get("x-mira-global-portal-action") != "1":
        raise HTTPException(403, "Ação do portal não autorizada.")


async def _scope(db: AsyncSession) -> None:
    # Transaction-local RLS context only inside the separate global auth module.
    await db.execute(text("SELECT set_config('app.global_identity_service', 'enabled', true)"))


def _digest(secret: str, purpose: str, value: str) -> str:
    return hmac.new(secret.encode(), (purpose + ":" + value).encode(), hashlib.sha256).hexdigest()


def _cpf(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    if len(digits) != 11 or len(set(digits)) == 1:
        raise ValueError("CPF inválido.")
    for n in (9, 10):
        digit = ((sum(int(digits[i]) * (n + 1 - i) for i in range(n)) * 10) % 11) % 10
        if digit != int(digits[n]):
            raise ValueError("CPF inválido.")
    return digits


class CPFInput(BaseModel):
    cpf: str = Field(max_length=20, min_length=11)

    @field_validator("cpf")
    @classmethod
    def validate_cpf(cls, value: str) -> str:
        return _cpf(value)


class RegistrationInput(CPFInput):
    email: str = Field(max_length=255, min_length=5)
    whatsapp: str = Field(max_length=24, min_length=11)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        result = value.strip().lower()
        if not _EMAIL.fullmatch(result):
            raise ValueError("E-mail inválido.")
        return result

    @field_validator("whatsapp")
    @classmethod
    def validate_whatsapp(cls, value: str) -> str:
        result = re.sub(r"\D", "", value)
        if not _PHONE.fullmatch(result):
            raise ValueError("WhatsApp inválido; informe DDI 55 e DDD.")
        return result


class VerificationInput(CPFInput):
    code: str = Field(pattern=r"^[0-9]{6}$")


class IdentityAttestationInput(BaseModel):
    account_id: UUID
    cpf_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    provider: str = Field(min_length=2, max_length=60, pattern=r"^[a-z0-9_-]+$")
    verified_at: datetime
    nonce: str = Field(min_length=24, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")


async def _throttle(request: Request, secret: str, cpf_digest: str, *, verify: bool = False) -> None:
    """Redis atomic request caps; no local-memory fallback across Render replicas."""
    settings = get_settings()
    source = request.client.host if request.client else "unknown"
    ip = _digest(secret, "ip", source)
    prefix = "mira:gportal:verify:" if verify else "mira:gportal:request:"
    keys = [prefix + "cpf:" + cpf_digest, prefix + "ip:" + ip]
    caps = (12, 60) if verify else (5, 100)
    ttl = 3600
    script = """
    for i=1,#KEYS do
      local current = tonumber(redis.call('GET',KEYS[i]) or '0')
      if current >= tonumber(ARGV[i]) then return 0 end
    end
    for i=1,#KEYS do
      local n=redis.call('INCR',KEYS[i])
      if n==1 then redis.call('EXPIRE',KEYS[i],ARGV[3]) end
    end
    return 1
    """
    try:
        client = redis.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=2)
        try:
            result = await client.eval(script, len(keys), *keys, *caps, ttl)
        finally:
            await client.aclose()
    except Exception as exc:
        raise HTTPException(503, "Verificação de segurança indisponível.") from exc
    if result != 1:
        raise HTTPException(429, "Muitas tentativas. Tente novamente mais tarde.")


async def _challenge(db: AsyncSession, account: GlobalStudentAccount, secret: str, purpose: str) -> str:
    now = _now()
    # Account is locked by caller. Rate/cooldown is enforced in Redis.
    await db.execute(update(GlobalStudentChallenge).where(
        GlobalStudentChallenge.account_id == account.id,
        GlobalStudentChallenge.consumed_at.is_(None),
    ).values(consumed_at=now))
    code = f"{secrets.randbelow(1_000_000):06d}"
    db.add(GlobalStudentChallenge(
        account_id=account.id,
        purpose=purpose,
        code_digest=_digest(secret, "otp:" + account.id, code),
        expires_at=now + _OTP_TTL,
    ))
    await db.commit()
    return code


async def _deliver(db: AsyncSession, account: GlobalStudentAccount, secret: str, purpose: str) -> None:
    code = await _challenge(db, account, secret, purpose)
    plain, html = access_code_email(code, ttl_minutes=5)
    delivery = await send_email_resend(to=account.email, subject="Seu código de acesso ao Portal MIRA",
                                      body=plain, html=html)
    if not delivery.ok:
        # Keep generic response to avoid revealing whether an account exists.
        await _scope(db)
        await db.execute(update(GlobalStudentChallenge).where(
            GlobalStudentChallenge.account_id == account.id,
            GlobalStudentChallenge.consumed_at.is_(None),
        ).values(consumed_at=_now()))
        await db.commit()


@router.post("/auth/register/request", status_code=202)
async def request_registration(body: RegistrationInput, request: Request, db: AsyncSession = Depends(get_db)):
    secret = _configured()
    _action(request)
    cpf_digest = _digest(secret, "cpf", body.cpf)
    await _throttle(request, secret, cpf_digest)
    await _scope(db)
    # Atomic insert: competing requests for same CPF cannot create two accounts.
    from sqlalchemy.dialects.postgresql import insert
    await db.execute(insert(GlobalStudentAccount).values(
        id=str(uuid4()), cpf_digest=cpf_digest, email=body.email, whatsapp=body.whatsapp,
    ).on_conflict_do_nothing(index_elements=["cpf_digest"]))
    account = (await db.execute(select(GlobalStudentAccount).where(
        GlobalStudentAccount.cpf_digest == cpf_digest,
    ).with_for_update())).scalar_one()
    if account.is_active and account.email_verified_at is None and account.email == body.email:
        await _deliver(db, account, secret, "register")
    else:
        await db.commit()
    return _GENERIC


@router.post("/auth/login/request", status_code=202)
async def request_login(body: CPFInput, request: Request, db: AsyncSession = Depends(get_db)):
    secret = _configured()
    _action(request)
    cpf_digest = _digest(secret, "cpf", body.cpf)
    await _throttle(request, secret, cpf_digest)
    await _scope(db)
    account = (await db.execute(select(GlobalStudentAccount).where(
        GlobalStudentAccount.cpf_digest == cpf_digest,
    ).with_for_update())).scalar_one_or_none()
    if account and account.is_active and account.email_verified_at is not None:
        await _deliver(db, account, secret, "login")
    else:
        await db.rollback()
    return _GENERIC


@router.post("/auth/verify")
async def verify_code(body: VerificationInput, request: Request, response: Response,
                      db: AsyncSession = Depends(get_db)):
    secret = _configured()
    _action(request)
    cpf_digest = _digest(secret, "cpf", body.cpf)
    await _throttle(request, secret, cpf_digest, verify=True)
    await _scope(db)
    account = (await db.execute(select(GlobalStudentAccount).where(
        GlobalStudentAccount.cpf_digest == cpf_digest,
        GlobalStudentAccount.is_active.is_(True),
    ).with_for_update())).scalar_one_or_none()
    if account is None:
        raise HTTPException(401, _INVALID)
    challenge = (await db.execute(select(GlobalStudentChallenge).where(
        GlobalStudentChallenge.account_id == account.id,
        GlobalStudentChallenge.consumed_at.is_(None),
    ).order_by(GlobalStudentChallenge.created_at.desc(), GlobalStudentChallenge.id.desc())
      .limit(1).with_for_update())).scalar_one_or_none()
    if not challenge or challenge.expires_at <= _now() or challenge.attempts >= 5:
        raise HTTPException(401, _INVALID)
    expected = _digest(secret, "otp:" + account.id, body.code)
    if not hmac.compare_digest(expected, challenge.code_digest):
        challenge.attempts += 1
        if challenge.attempts >= 5:
            challenge.consumed_at = _now()
        await db.commit()
        raise HTTPException(401, _INVALID)
    if challenge.purpose == "login" and account.email_verified_at is None:
        raise HTTPException(401, _INVALID)
    now = _now()
    challenge.consumed_at = now
    if challenge.purpose == "register":
        account.email_verified_at = now
        # This is NOT proof of CPF ownership and does not unlock debts.
    token = secrets.token_urlsafe(48)
    db.add(GlobalStudentSession(
        account_id=account.id,
        token_digest=_digest(secret, "session", token),
        expires_at=now + _SESSION_TTL,
    ))
    await db.commit()
    response.set_cookie(_COOKIE, token, max_age=int(_SESSION_TTL.total_seconds()),
                        httponly=True, secure=get_settings().app_env not in {"development", "testing"},
                        samesite="lax", path="/")
    response.headers["Cache-Control"] = "no-store"
    return {"authenticated": True, "identity_verified": bool(account.identity_verified_at),
            "requires_identity_verification": account.identity_verified_at is None}


async def _session(request: Request, db: AsyncSession, secret: str):
    token = request.cookies.get(_COOKIE, "")
    if not token:
        raise HTTPException(401, "Sessão inválida ou expirada.")
    await _scope(db)
    session = (await db.execute(select(GlobalStudentSession).where(
        GlobalStudentSession.token_digest == _digest(secret, "session", token),
        GlobalStudentSession.revoked_at.is_(None),
        GlobalStudentSession.expires_at > _now(),
    ))).scalar_one_or_none()
    if not session:
        raise HTTPException(401, "Sessão inválida ou expirada.")
    account = await db.get(GlobalStudentAccount, session.account_id)
    if not account or not account.is_active or not account.email_verified_at:
        raise HTTPException(401, "Sessão inválida ou expirada.")
    return session, account


@router.get("/auth/me")
async def me(request: Request, db: AsyncSession = Depends(get_db)):
    secret = _configured()
    _, account = await _session(request, db, secret)
    return {"authenticated": True, "email": account.email, "whatsapp": account.whatsapp,
            "identity_verified": bool(account.identity_verified_at),
            "requires_identity_verification": account.identity_verified_at is None,
            "debts_available": False, "agreements_available": False}


@router.post("/auth/logout")
async def logout(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    secret = _configured()
    _action(request)
    session, _ = await _session(request, db, secret)
    session.revoked_at = _now()
    await db.commit()
    response.delete_cookie(_COOKIE, path="/")
    response.headers["Cache-Control"] = "no-store"
    return {"authenticated": False}


@router.post("/auth/identity/attest")
async def provider_attestation(
    body: IdentityAttestationInput, request: Request,
    x_mira_identity_signature: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Signed assertion ONLY from an independently contracted identity provider.

    No public student UI can call this. Requires independent provider evidence,
    a dedicated secret, a fresh signature and a one-time nonce. Disabled by default.
    """
    secret = _configured()
    settings = get_settings()
    proof_secret = getattr(settings, "global_student_identity_proof_secret", None)
    if not (settings.global_student_identity_proof_enabled and proof_secret and len(proof_secret) >= 32):
        raise HTTPException(503, "Verificação externa de titularidade não habilitada.")
    verified_at = body.verified_at.astimezone(timezone.utc)
    if body.verified_at.utcoffset() is None or abs((_now() - verified_at).total_seconds()) > 300:
        raise HTTPException(401, "Atestado inválido ou expirado.")
    message = "|".join((str(body.account_id), body.cpf_digest, body.provider,
                        verified_at.isoformat(), body.nonce))
    expected = hmac.new(proof_secret.encode(), message.encode(), hashlib.sha256).hexdigest()
    if not x_mira_identity_signature or not hmac.compare_digest(
        "v1=" + expected, x_mira_identity_signature
    ):
        raise HTTPException(401, "Atestado inválido.")
    await _scope(db)
    account = (await db.execute(select(GlobalStudentAccount).where(
        GlobalStudentAccount.id == str(body.account_id),
        GlobalStudentAccount.cpf_digest == body.cpf_digest,
        GlobalStudentAccount.email_verified_at.is_not(None),
        GlobalStudentAccount.is_active.is_(True),
    ).with_for_update())).scalar_one_or_none()
    if account is None:
        raise HTTPException(401, "Atestado inválido.")
    nonce_digest = _digest(secret, "identity-attestation", body.nonce)
    prior = await db.get(GlobalStudentAttestation, nonce_digest)
    if prior is not None:
        raise HTTPException(409, "Atestado já processado.")
    db.add(GlobalStudentAttestation(
        nonce_digest=nonce_digest, account_id=account.id,
        provider=body.provider, verified_at=verified_at,
    ))
    account.identity_verified_at = verified_at
    account.identity_verification_method = body.provider
    await db.commit()
    return {"accepted": True}
