"""Primitivos de autenticação do Mira, sem dependências criptográficas externas."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Optional

from app.core.config import get_settings

_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
TOKEN_TTL_SECONDS = 60 * 60
_TOKEN_TTL_SECONDS = TOKEN_TTL_SECONDS


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64url(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=64)
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${_b64url(salt)}${_b64url(digest)}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, n, r, p, salt_b64, digest_b64 = stored_hash.split("$", 5)
        if algorithm != "scrypt":
            return False
        expected = _unb64url(digest_b64)
        actual = hashlib.scrypt(
            password.encode("utf-8"), salt=_unb64url(salt_b64), n=int(n), r=int(r), p=int(p), dklen=len(expected)
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError, MemoryError):
        return False


def issue_access_token(
    *,
    user_id: str,
    tenant_id: str,
    auth_version: int,
    session_id: str,
    aal: int = 1,
    membership_id: Optional[str] = None,
    authenticated_at: Optional[int] = None,
) -> tuple[str, int]:
    now = int(time.time())
    claims = {
        "iss": "mira",
        "sub": user_id,
        "tid": tenant_id,
        "ver": auth_version,
        "aal": aal,
        "sid": session_id,
        "purpose": "session",
        "iat": now,
        "auth_time": int(authenticated_at if authenticated_at is not None else now),
        "exp": now + _TOKEN_TTL_SECONDS,
    }
    if membership_id:
        claims["mid"] = membership_id
    header = {"alg": "HS256", "typ": "JWT"}
    unsigned = f"{_b64url(json.dumps(header, separators=(',', ':')).encode())}.{_b64url(json.dumps(claims, separators=(',', ':')).encode())}"
    secret = get_settings().secret_key.encode("utf-8")
    signature = hmac.new(secret, unsigned.encode("ascii"), hashlib.sha256).digest()
    return f"{unsigned}.{_b64url(signature)}", _TOKEN_TTL_SECONDS


def decode_access_token(token: str) -> dict | None:
    try:
        encoded_header, encoded_claims, encoded_signature = token.split(".")
        unsigned = f"{encoded_header}.{encoded_claims}"
        expected = hmac.new(
            get_settings().secret_key.encode("utf-8"), unsigned.encode("ascii"), hashlib.sha256
        ).digest()
        if not hmac.compare_digest(expected, _unb64url(encoded_signature)):
            return None
        header = json.loads(_unb64url(encoded_header))
        claims = json.loads(_unb64url(encoded_claims))
        if header != {"alg": "HS256", "typ": "JWT"}:
            return None
        now = int(time.time())
        issued_at = int(claims.get("iat", 0))
        auth_time = int(claims.get("auth_time", issued_at))
        if (
            claims.get("iss") != "mira"
            or int(claims.get("exp", 0)) <= now
            or issued_at <= 0
            or issued_at > now + 60
            or auth_time <= 0
            or auth_time > issued_at + 60
        ):
            return None
        if not claims.get("sub") or not claims.get("tid"):
            return None
        return claims
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        return None
