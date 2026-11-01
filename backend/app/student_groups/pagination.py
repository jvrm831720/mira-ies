"""Codificação e validação de cursores protegidos para grupos virtuais."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

from app.core.config import get_settings
from app.student_groups.catalog import GROUP_CATALOG_VERSION

CURSOR_TTL_SECONDS = 60 * 60


class InvalidGroupCursor(ValueError):
    """Cursor inválido, adulterado ou incompatível com a consulta."""


class ExpiredGroupCursor(InvalidGroupCursor):
    """Cursor assinado cuja janela de validade terminou."""


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _signature(unsigned: str) -> str:
    key = get_settings().secret_key.encode("utf-8")
    digest = hmac.new(key, unsigned.encode("ascii"), hashlib.sha256).digest()
    return _b64encode(digest)


def create_group_cursor(
    *,
    tenant_id: str,
    group_id: str,
    after_id: str,
    last_member_id: str | None,
    limit: int,
    now: int | None = None,
) -> str:
    issued_at = int(time.time() if now is None else now)
    payload = {
        "v": 1,
        "tenant_id": tenant_id,
        "group_id": group_id,
        "catalog_version": GROUP_CATALOG_VERSION,
        "after_id": after_id,
        "last_member_id": last_member_id,
        "limit": limit,
        "iat": issued_at,
        "exp": issued_at + CURSOR_TTL_SECONDS,
    }
    encoded_payload = _b64encode(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    unsigned = f"{encoded_payload}"
    return f"{unsigned}.{_signature(unsigned)}"


def decode_group_cursor(
    cursor: str,
    *,
    tenant_id: str,
    group_id: str,
    now: int | None = None,
) -> dict[str, Any]:
    """Validate syntax, signature, expiry and every query binding."""
    if not cursor or len(cursor) > 4096 or cursor.count(".") != 1:
        raise InvalidGroupCursor("invalid")
    encoded_payload, supplied_signature = cursor.split(".", 1)
    try:
        expected_signature = _signature(encoded_payload)
        if not hmac.compare_digest(expected_signature, supplied_signature):
            raise InvalidGroupCursor("invalid")
        payload = json.loads(_b64decode(encoded_payload))
    except InvalidGroupCursor:
        raise
    except Exception as exc:
        raise InvalidGroupCursor("invalid") from exc

    if not isinstance(payload, dict):
        raise InvalidGroupCursor("invalid")
    required = {
        "v",
        "tenant_id",
        "group_id",
        "catalog_version",
        "after_id",
        "last_member_id",
        "limit",
        "iat",
        "exp",
    }
    if set(payload) != required:
        raise InvalidGroupCursor("invalid")
    if payload.get("tenant_id") != tenant_id or payload.get("group_id") != group_id:
        raise InvalidGroupCursor("invalid")
    if payload.get("catalog_version") != GROUP_CATALOG_VERSION or payload.get("v") != 1:
        raise InvalidGroupCursor("invalid")
    if (
        not isinstance(payload.get("after_id"), str)
        or not payload["after_id"]
        or not isinstance(payload.get("limit"), int)
        or isinstance(payload.get("limit"), bool)
        or payload["limit"] < 1
        or payload["limit"] > 100
    ):
        raise InvalidGroupCursor("invalid")
    last_member_id = payload.get("last_member_id")
    if last_member_id is not None and (
        not isinstance(last_member_id, str) or not last_member_id
    ):
        raise InvalidGroupCursor("invalid")
    issued_at, expires_at = payload.get("iat"), payload.get("exp")
    if (
        not isinstance(issued_at, int)
        or isinstance(issued_at, bool)
        or not isinstance(expires_at, int)
        or isinstance(expires_at, bool)
        or expires_at <= issued_at
        or expires_at - issued_at > CURSOR_TTL_SECONDS
    ):
        raise InvalidGroupCursor("invalid")
    current_time = int(time.time() if now is None else now)
    if expires_at <= current_time:
        raise ExpiredGroupCursor("expired")
    return payload
