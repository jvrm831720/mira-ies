"""Encryption domain for Frappe site API credentials.

Never expose the encrypted fields through REST or serialize these ORM models.
"""
from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


class EducationEngineSecretError(RuntimeError):
    pass


def _fernet() -> Fernet:
    secret = get_settings().secret_key
    if len(secret) < 32 or "change-this" in secret.lower():
        raise EducationEngineSecretError("Configure SECRET_KEY segura e estável no Render.")
    digest = hashlib.sha256(("mira:education-engine:token:v1:" + secret).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_credential(value: str) -> str:
    if not isinstance(value, str) or not value or any(ord(ch) < 33 or ord(ch) == 127 for ch in value):
        raise ValueError("Credencial Frappe inválida.")
    return _fernet().encrypt(value.encode()).decode("ascii")


def decrypt_credential(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeDecodeError, ValueError) as exc:
        raise EducationEngineSecretError("Credencial de integração indisponível.") from exc
