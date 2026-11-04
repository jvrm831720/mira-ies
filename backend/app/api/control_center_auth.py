"""Autenticação independente do Control Center: senha + código MFA por e-mail."""
from __future__ import annotations

import binascii
import hashlib
import hmac
import json
import logging
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis

from app.core.config import get_settings
from app.core.mira_security import hash_password, verify_password
from app.db.session import get_db
from app.models.control_center import AdminAuditEvent, AdminEmailChallenge, AdminPrincipal
from app.agents.providers.resend_provider import send_email_resend

router = APIRouter(prefix="/admin/control-center/auth", tags=["MIRA Control Center - Auth"])
logger = logging.getLogger(__name__)
_DUMMY_PASSWORD_HASH = hash_password(secrets.token_urlsafe(32))
_bearer = HTTPBearer(auto_error=False)

_CODE_TTL_SECONDS = 300
_CODE_COOLDOWN_SECONDS = 60
_MAX_CODE_ATTEMPTS = 5
_MAX_PASSWORD_ATTEMPTS = 8
_LOCK_MINUTES = 15
_TOKEN_TTL_SECONDS = 20 * 60
_ACTION_CODE_TTL_SECONDS = 300
_ACTION_CODE_ATTEMPTS = 5
_HIGH_RISK_ACTIONS = {"organization_deactivate", "member_permission_change"}
_ALLOWED_ROLES = {"super_admin", "operations", "finance", "support", "auditor"}
_ROLE_PERMISSIONS = {
    "super_admin": {"*"},
    "operations": {"ops:read", "channels:read", "channels:write", "orgs:read"},
    "finance": {"billing:read", "billing:write", "plans:read", "plans:write", "orgs:read"},
    "support": {"orgs:read", "members:read", "channels:read"},
    "auditor": {"audit:read", "governance:read", "ops:read", "billing:read", "plans:read", "orgs:read"},
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _enforce_rate_limit(
    request: Request,
    scope: str,
    limit: int,
    window_seconds: int,
    identity: str,
) -> None:
    """Distributed per-account rate limit; fail closed if Redis is unavailable.

    The API is called server-to-server by the frontend BFF, so request.client.host
    may be the shared BFF address rather than the human operator. Never use that
    shared address as the primary login throttle, and never trust unvalidated
    X-Forwarded-For headers. Use a keyed digest of the normalized account identity.
    """
    settings = get_settings()
    subject = f"identity:{identity.strip().lower()}"
    key = _digest("rate-limit", f"{scope}:{subject}")
    redis = Redis.from_url(settings.redis_url, decode_responses=True, socket_connect_timeout=2, socket_timeout=2)
    try:
        count = await redis.incr(f"mira:control-center:rl:{key}")
        if count == 1:
            await redis.expire(f"mira:control-center:rl:{key}", window_seconds)
        if count > limit:
            raise HTTPException(status_code=429, detail="Muitas tentativas. Aguarde antes de tentar novamente.")
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Redis indisponível para rate limit do Control Center: %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Autenticação temporariamente indisponível.") from exc
    finally:
        await redis.aclose()


def _normal_email(email: str) -> str:
    return email.strip().lower()


def _digest(kind: str, value: str) -> str:
    secret = get_settings().secret_key.encode("utf-8")
    return hmac.new(secret, f"mira-control-center:{kind}:{value}".encode(), hashlib.sha256).hexdigest()


def _b64(data: bytes) -> str:
    import base64
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(value: str) -> bytes:
    import base64
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _issue_token(admin: AdminPrincipal) -> str:
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    claims = {
        "iss": "mira-control-center", "aud": "mira-control-center",
        "sub": admin.id, "role": admin.role, "ver": admin.auth_version,
        "iat": now, "mfa_at": now, "exp": now + _TOKEN_TTL_SECONDS,
    }
    unsigned = f"{_b64(json.dumps(header, separators=(',', ':')).encode())}.{_b64(json.dumps(claims, separators=(',', ':')).encode())}"
    signature = hmac.new(get_settings().secret_key.encode(), unsigned.encode("ascii"), hashlib.sha256).digest()
    return f"{unsigned}.{_b64(signature)}"


def _decode_token(token: str) -> dict | None:
    try:
        encoded_header, encoded_claims, encoded_signature = token.split(".")
        unsigned = f"{encoded_header}.{encoded_claims}"
        expected = hmac.new(get_settings().secret_key.encode(), unsigned.encode("ascii"), hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _unb64(encoded_signature)):
            return None
        header, claims = json.loads(_unb64(encoded_header)), json.loads(_unb64(encoded_claims))
        if header != {"alg": "HS256", "typ": "JWT"}:
            return None
        if claims.get("iss") != "mira-control-center" or claims.get("aud") != "mira-control-center":
            return None
        if int(claims.get("exp", 0)) <= int(time.time()):
            return None
        return claims
    except (ValueError, TypeError, KeyError, json.JSONDecodeError, binascii.Error, UnicodeDecodeError, OverflowError):
        return None


async def _audit(db: AsyncSession, action: str, result: str, actor_id: str | None = None,
                 request: Request | None = None, reason: str | None = None) -> None:
    db.add(AdminAuditEvent(
        actor_admin_id=actor_id, action=action, result=result, reason=reason,
        request_id=request.headers.get("x-request-id") if request else None,
        metadata_redacted={"path": request.url.path, "method": request.method} if request else None,
    ))


class PasswordPayload(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=1, max_length=256)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if "@" not in normalized or normalized.count("@") != 1 or "." not in normalized.rsplit("@", 1)[-1] or any(ch.isspace() for ch in normalized):
            raise ValueError("Informe um e-mail válido.")
        return normalized


class VerifyEmailCodePayload(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    code: str = Field(pattern=r"^\d{6}$")

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if "@" not in normalized or normalized.count("@") != 1 or "." not in normalized.rsplit("@", 1)[-1] or any(ch.isspace() for ch in normalized):
            raise ValueError("Informe um e-mail válido.")
        return normalized


class AdminSession(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = _TOKEN_TTL_SECONDS
    role: str


@router.post("/login", status_code=202)
async def start_admin_login(body: PasswordPayload, request: Request, db: AsyncSession = Depends(get_db)):
    email = _normal_email(str(body.email))
    await _enforce_rate_limit(request, "login_email", 10, 300, identity=email)
    result = await db.execute(select(AdminPrincipal).where(AdminPrincipal.email == email).with_for_update())
    admin = result.scalar_one_or_none()
    now = _now()

    if admin and admin.locked_until and admin.locked_until > now:
        await _audit(db, "admin_login_password", "blocked", admin.id, request)
        await db.commit()
        raise HTTPException(status_code=429, detail="Acesso temporariamente bloqueado. Tente mais tarde.")

    password_ok = verify_password(body.password, admin.password_hash if admin else _DUMMY_PASSWORD_HASH)
    if not admin or not admin.is_active or admin.role not in _ALLOWED_ROLES or not password_ok:
        if admin:
            admin.failed_login_attempts += 1
            if admin.failed_login_attempts >= _MAX_PASSWORD_ATTEMPTS:
                admin.failed_login_attempts = 0
                admin.locked_until = now + timedelta(minutes=_LOCK_MINUTES)
        await _audit(db, "admin_login_password", "denied", admin.id if admin else None, request)
        await db.commit()
        raise HTTPException(status_code=401, detail="Credenciais inválidas.")

    email_hash = _digest("email", email)
    recent = await db.execute(select(AdminEmailChallenge.id).where(
        AdminEmailChallenge.email_hash == email_hash,
        AdminEmailChallenge.created_at >= now - timedelta(seconds=_CODE_COOLDOWN_SECONDS),
    ).limit(1))
    if recent.scalar_one_or_none():
        raise HTTPException(status_code=429, detail="Aguarde antes de solicitar outro código.")

    admin.failed_login_attempts = 0
    admin.locked_until = None
    code = f"{secrets.randbelow(1_000_000):06d}"
    await db.execute(update(AdminEmailChallenge).where(
        AdminEmailChallenge.email_hash == email_hash,
        AdminEmailChallenge.consumed_at.is_(None),
    ).values(consumed_at=now))
    challenge = AdminEmailChallenge(
        admin_id=admin.id, email_hash=email_hash, code_hash=_digest("otp", f"{email}:{code}"),
        expires_at=now + timedelta(seconds=_CODE_TTL_SECONDS),
    )
    db.add(challenge)
    await _audit(db, "admin_login_password", "mfa_pending", admin.id, request)
    await db.commit()

    settings = get_settings()
    if not settings.resend_api_key or not settings.email_from:
        challenge.consumed_at = _now()
        await db.commit()
        logger.error("Control Center MFA email provider is not configured.")
        raise HTTPException(status_code=503, detail="MFA por e-mail indisponível. Contate a equipe responsável.")

    delivery = await send_email_resend(
        to=admin.email,
        subject="Código de acesso — MIRA Control Center",
        body=f"Olá, {admin.display_name}.\n\nSeu código de acesso é {code}. Ele expira em 5 minutos e só pode ser usado uma vez. Não compartilhe este código.\n\nSe você não solicitou o acesso, ignore este e-mail.",
    )
    if not delivery.ok:
        challenge.consumed_at = _now()
        await db.commit()
        logger.warning("Falha na entrega do código MFA do Control Center.")
        raise HTTPException(status_code=503, detail="Não foi possível enviar o código MFA. Tente novamente mais tarde.")

    return {"message": "Se as credenciais forem válidas, enviaremos um código de acesso.", "expires_in": _CODE_TTL_SECONDS}


@router.post("/verify", response_model=AdminSession)
async def verify_admin_email_code(body: VerifyEmailCodePayload, request: Request, db: AsyncSession = Depends(get_db)):
    email = _normal_email(str(body.email))
    await _enforce_rate_limit(request, "mfa_verify_email", 10, 300, identity=email)
    email_hash = _digest("email", email)
    result = await db.execute(select(AdminEmailChallenge).where(
        AdminEmailChallenge.email_hash == email_hash,
        AdminEmailChallenge.consumed_at.is_(None),
    ).order_by(AdminEmailChallenge.created_at.desc()).limit(1).with_for_update())
    challenge = result.scalar_one_or_none()
    now = _now()
    if not challenge or challenge.expires_at <= now:
        if challenge:
            challenge.consumed_at = now
        await _audit(db, "admin_mfa_verify", "denied", challenge.admin_id if challenge else None, request)
        await db.commit()
        raise HTTPException(status_code=401, detail="Código inválido ou expirado.")
    if challenge.attempts >= _MAX_CODE_ATTEMPTS:
        challenge.consumed_at = now
        await _audit(db, "admin_mfa_verify", "rate_limited", challenge.admin_id, request)
        await db.commit()
        raise HTTPException(status_code=429, detail="Limite de tentativas atingido. Inicie o login novamente.")

    challenge.attempts += 1
    expected = _digest("otp", f"{email}:{body.code}")
    if not hmac.compare_digest(challenge.code_hash, expected):
        if challenge.attempts >= _MAX_CODE_ATTEMPTS:
            challenge.consumed_at = now
        await _audit(db, "admin_mfa_verify", "denied", challenge.admin_id, request)
        await db.commit()
        raise HTTPException(status_code=401, detail="Código inválido ou expirado.")

    challenge.consumed_at = now
    admin = await db.get(AdminPrincipal, challenge.admin_id)
    if not admin or not admin.is_active:
        await _audit(db, "admin_mfa_verify", "denied", challenge.admin_id, request)
        await db.commit()
        raise HTTPException(status_code=401, detail="Código inválido ou expirado.")
    await _audit(db, "admin_mfa_verify", "success", admin.id, request)
    await db.commit()
    return AdminSession(access_token=_issue_token(admin), role=admin.role)


async def require_admin_permission(permission: str, credentials: HTTPAuthorizationCredentials | None = Security(_bearer),
                                   db: AsyncSession = Depends(get_db)) -> AdminPrincipal:
    if not credentials:
        raise HTTPException(status_code=401, detail="Autenticação interna necessária.")
    claims = _decode_token(credentials.credentials)
    if not claims:
        raise HTTPException(status_code=401, detail="Sessão administrativa inválida ou expirada.")
    admin = await db.get(AdminPrincipal, claims.get("sub"))
    if not admin or not admin.is_active or admin.auth_version != claims.get("ver"):
        raise HTTPException(status_code=401, detail="Sessão administrativa inválida ou expirada.")
    permissions = _ROLE_PERMISSIONS.get(admin.role, set())
    if "*" not in permissions and permission not in permissions:
        raise HTTPException(status_code=403, detail="Permissão insuficiente.")
    return admin


def admin_permission(permission: str) -> Callable:
    async def dependency(credentials: HTTPAuthorizationCredentials | None = Security(_bearer),
                         db: AsyncSession = Depends(get_db)) -> AdminPrincipal:
        return await require_admin_permission(permission, credentials, db)
    return dependency


class ActionConfirmationPayload(BaseModel):
    action: str = Field(min_length=3, max_length=100)
    target_id: str = Field(min_length=1, max_length=100)
    payload: dict


def _action_payload_hash(action: str, target_id: str, payload: dict) -> str:
    serialized = json.dumps({"action": action, "target_id": target_id, "payload": payload}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return _digest("high-risk-action", serialized)


@router.post("/action-confirmations", status_code=202)
async def request_action_confirmation(
    body: ActionConfirmationPayload, request: Request,
    admin: AdminPrincipal = Depends(admin_permission("orgs:read")),
    db: AsyncSession = Depends(get_db),
):
    action = body.action.strip()
    allowed = {"organization_update", "organization_deactivate", "member_update", "member_permission_change", "billing_record_create", "billing_record_update"}
    if action not in allowed:
        raise HTTPException(status_code=422, detail="Ação não habilitada para confirmação.")
    credentials = request.headers.get("authorization", "").removeprefix("Bearer ")
    claims = _decode_token(credentials)
    if action in _HIGH_RISK_ACTIONS and (not claims or int(claims.get("mfa_at", 0)) < int(time.time()) - 300):
        await _audit(db, "high_risk_confirmation_request", "mfa_required", admin.id, request)
        await db.commit()
        raise HTTPException(status_code=401, detail="MFA recente obrigatório. Entre novamente e solicite a confirmação.")
    await _enforce_rate_limit(request, "action_confirmation", 5, 300, identity=admin.email)
    now = _now()
    email_hash = _digest("email", admin.email)
    recent = await db.execute(select(AdminEmailChallenge.id).where(AdminEmailChallenge.email_hash == email_hash, AdminEmailChallenge.purpose == "action", AdminEmailChallenge.created_at >= now - timedelta(seconds=_CODE_COOLDOWN_SECONDS)).limit(1))
    if recent.scalar_one_or_none():
        raise HTTPException(status_code=429, detail="Aguarde antes de solicitar outro código.")
    code = f"{secrets.randbelow(1_000_000):06d}"
    await db.execute(update(AdminEmailChallenge).where(AdminEmailChallenge.admin_id == admin.id, AdminEmailChallenge.purpose == "action", AdminEmailChallenge.consumed_at.is_(None)).values(consumed_at=now))
    challenge = AdminEmailChallenge(admin_id=admin.id, email_hash=email_hash, code_hash=_digest("otp", f"{admin.email}:{code}"), purpose="action", action_key=action, payload_hash=_action_payload_hash(action, body.target_id, body.payload), expires_at=now + timedelta(seconds=_ACTION_CODE_TTL_SECONDS))
    db.add(challenge)
    await _audit(db, "high_risk_confirmation_requested", "pending", admin.id, request, reason=action)
    await db.commit()
    settings = get_settings()
    if not settings.resend_api_key or not settings.email_from:
        challenge.consumed_at = _now(); await db.commit()
        raise HTTPException(status_code=503, detail="Confirmação por e-mail indisponível.")
    delivery = await send_email_resend(to=admin.email, subject="Confirmação de ação crítica — MIRA", body=f"Solicitação: {action} (alvo {body.target_id}). Código: {code}. Expira em 5 minutos, uso único. Se não reconhece a ação, ignore este e-mail.")
    if not delivery.ok:
        challenge.consumed_at = _now(); await db.commit()
        raise HTTPException(status_code=503, detail="Não foi possível enviar a confirmação por e-mail.")
    return {"message": "Código enviado ao e-mail cadastrado.", "expires_in": _ACTION_CODE_TTL_SECONDS, "challenge_id": challenge.id}


async def consume_action_confirmation(db: AsyncSession, request: Request, admin: AdminPrincipal, action: str, target_id: str, payload: dict) -> None:
    challenge_id = request.headers.get("x-confirmation-id")
    code = request.headers.get("x-confirmation-code", "")
    result = await db.execute(select(AdminEmailChallenge).where(AdminEmailChallenge.id == challenge_id, AdminEmailChallenge.admin_id == admin.id, AdminEmailChallenge.purpose == "action", AdminEmailChallenge.consumed_at.is_(None)).with_for_update())
    challenge = result.scalar_one_or_none()
    now = _now()
    valid = bool(challenge and challenge.expires_at > now and challenge.attempts < _ACTION_CODE_ATTEMPTS)
    if not valid:
        await _audit(db, "high_risk_action", "denied", admin.id, request, reason=action); await db.commit()
        raise HTTPException(status_code=401, detail="Confirmação ausente, inválida ou expirada.")
    challenge.attempts += 1
    matches = challenge.action_key == action and hmac.compare_digest(challenge.payload_hash or "", _action_payload_hash(action, target_id, payload)) and hmac.compare_digest(challenge.code_hash, _digest("otp", f"{admin.email}:{code}"))
    if not matches:
        if challenge.attempts >= _ACTION_CODE_ATTEMPTS: challenge.consumed_at = now
        await _audit(db, "high_risk_action_confirmation", "denied", admin.id, request, reason=action); await db.commit()
        raise HTTPException(status_code=401, detail="Confirmação inválida para esta ação.")
    challenge.consumed_at = now
    await _audit(db, "high_risk_action_confirmation", "confirmed", admin.id, request, reason=action)


@router.get("/me")
async def current_admin(admin: AdminPrincipal = Depends(admin_permission("orgs:read"))):
    return {"id": admin.id, "email": admin.email, "display_name": admin.display_name, "role": admin.role}
