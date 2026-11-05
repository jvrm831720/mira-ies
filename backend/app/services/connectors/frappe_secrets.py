"""Separate encryption domain for Frappe API key/secret; never return ciphertext to clients."""
from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from app.core.config import get_settings


class FrappeSecretError(RuntimeError):
    pass


def _cipher() -> Fernet:
    secret = get_settings().secret_key
    if len(secret) < 32 or "change-this" in secret.lower():
        raise FrappeSecretError("Configure SECRET_KEY segura antes de salvar credenciais Frappe.")
    key = hashlib.sha256(("mira:frappe-ies:v1:" + secret).encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_frappe_secret(value: str) -> str:
    if not value or any(ord(char) < 33 or ord(char) == 127 for char in value):
        raise ValueError("Credencial Frappe inválida.")
    return _cipher().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_frappe_secret(value: str) -> str:
    try:
        return _cipher().decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeDecodeError, ValueError) as exc:
        raise FrappeSecretError("Não foi possível recuperar a credencial Frappe.") from exc
