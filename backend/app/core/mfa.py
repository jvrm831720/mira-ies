"""Primitivos TOTP, criptografia do segredo e códigos de recuperação da MIRA."""
from __future__ import annotations

import base64
import hashlib
import hmac
import io
import secrets
import struct
import time
from datetime import datetime, timezone

from cryptography.fernet import Fernet
from app.core.config import get_settings


def _fernet() -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(get_settings().secret_key.encode("utf-8")).digest())
    return Fernet(key)


def encrypt_totp_secret(secret: str) -> str:
    return _fernet().encrypt(secret.encode("ascii")).decode("ascii")


def decrypt_totp_secret(ciphertext: str) -> str:
    return _fernet().decrypt(ciphertext.encode("ascii")).decode("ascii")


def new_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def totp_at(secret: str, timestamp: int | None = None, period: int = 30) -> tuple[str, int]:
    now = int(time.time()) if timestamp is None else int(timestamp)
    step = now // period
    padded = secret.upper() + "=" * (-len(secret) % 8)
    key = base64.b32decode(padded, casefold=True)
    digest = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    binary = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(binary % 1_000_000).zfill(6), step


def verify_totp(secret: str, code: str, last_step: int | None = None, window: int = 1) -> int | None:
    if len(code) != 6 or not code.isdigit():
        return None
    current = int(time.time()) // 30
    padded = secret.upper() + "=" * (-len(secret) % 8)
    key = base64.b32decode(padded, casefold=True)
    for step in range(current - window, current + window + 1):
        if last_step is not None and step <= last_step:
            continue
        digest = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
        offset = digest[-1] & 0x0F
        binary = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
        expected = str(binary % 1_000_000).zfill(6)
        if hmac.compare_digest(expected, code):
            return step
    return None


def recovery_code_hash(code: str) -> str:
    pepper = get_settings().secret_key.encode("utf-8")
    normalized = code.replace("-", "").replace(" ", "").upper()
    return hmac.new(pepper, b"mira:mfa-recovery:" + normalized.encode("ascii"), hashlib.sha256).hexdigest()


def generate_recovery_codes(count: int = 10) -> list[str]:
    return [secrets.token_hex(6).upper() for _ in range(count)]


def totp_qr_data_uri(secret: str, email: str) -> str:
    import qrcode
    import qrcode.image.svg

    issuer = "MIRA"
    label = f"{issuer}:{email}"
    uri = f"otpauth://totp/{label}?secret={secret}&issuer={issuer}&algorithm=SHA1&digits=6&period=30"
    image = qrcode.make(uri, image_factory=qrcode.image.svg.SvgPathImage)
    output = io.BytesIO()
    image.save(output)
    encoded = base64.b64encode(output.getvalue()).decode("ascii")
    return "data:image/svg+xml;base64," + encoded
