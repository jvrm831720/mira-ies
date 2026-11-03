"""Authenticated encryption helpers for tenant SophiA integration credentials."""
from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


class SophiaSecretError(RuntimeError):
    """Credential encryption/decryption failed."""


def _fernet() -> Fernet:
    secret = get_settings().secret_key
    if not secret or len(secret) < 32 or "change-this" in secret.lower():
        raise RuntimeError("A secure SECRET_KEY is required for SophiA credential storage.")
    digest = hashlib.sha256(("mira:sophia-credential:v1:" + secret).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_sophia_secret(value: str) -> str:
    if not value:
        raise ValueError("SophiA credential cannot be empty.")
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_sophia_secret(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeDecodeError) as exc:
        raise SophiaSecretError("Could not decrypt the stored SophiA credential.") from exc
