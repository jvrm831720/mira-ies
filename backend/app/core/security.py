"""Utilitarios de seguranca: geracao e verificacao de API keys."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Optional

from app.core.config import get_settings


def generate_api_key(prefix: str = "bkn") -> str:
    return f"{prefix}_{secrets.token_urlsafe(32)}"


def hash_api_key(raw_key: str) -> str:
    settings = get_settings()
    pepper = (settings.secret_key or "beacon-dev-pepper").encode("utf-8")
    return hmac.new(pepper, raw_key.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_api_key(raw_key: str, stored_hash: str) -> bool:
    if not raw_key or not stored_hash:
        return False
    return hmac.compare_digest(hash_api_key(raw_key), stored_hash)


def sign_webhook_body(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def verify_webhook_signature(body: bytes, signature: Optional[str], secret: Optional[str]) -> bool:
    if not secret:
        settings = get_settings()
        if settings.app_env == "development" and settings.allow_unsigned_webhooks:
            return True
        return False
    if not signature:
        return False
    expected = sign_webhook_body(body, secret)
    sig = signature.removeprefix("sha256=").strip()
    return hmac.compare_digest(expected, sig)
