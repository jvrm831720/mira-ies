"""Authenticated encryption for tenant Omie credentials."""
from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


class OmieSecretError(RuntimeError):
    """Omie credential encryption/decryption failed."""


def _fernet() -> Fernet:
    secret = get_settings().secret_key
    if not secret or len(secret) < 32 or "change-this" in secret.lower():
        raise RuntimeError("A secure SECRET_KEY is required for Omie credential storage.")
    digest = hashlib.sha256(("mira:omie-credential:v1:" + secret).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_omie_secret(value: str) -> str:
    if not value:
        raise ValueError("Omie credential cannot be empty.")
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_omie_secret(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeDecodeError) as exc:
        raise OmieSecretError("Could not decrypt the stored Omie credential.") from exc
