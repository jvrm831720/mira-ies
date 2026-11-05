"""Fail-closed policy and encrypted approval payload primitives for Composio.

This module never executes tools. It resolves tenant-owned authorization, validates
arguments against the live tool schema, and provides authenticated encryption for
the approval record. The executor remains a separate, disabled wave.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import secrets
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.auth import AuthContext
from app.core.config import get_settings
from app.models.composio_connection import (
    TenantComposioAccount,
    TenantComposioToolkitPolicy,
)
from app.services.composio.client import list_tools_for_toolkit
from app.services.composio.gateway import (
    composio_toolkit_allowed,
    require_composio_configuration,
)

_SENSITIVE_KEY = re.compile(
    r"(password|passwd|secret|token|authorization|cookie|api[_-]?key|"
    r"access[_-]?key|private[_-]?key|credential|email|phone|cpf|document|recipient|contact)",
    re.IGNORECASE,
)
_MAX_ARGUMENT_BYTES = 64 * 1024
_MAX_DEPTH = 12
_MAX_ITEMS = 500
_EMAIL_VALUE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_CPF_VALUE = re.compile(r"(?<!\d)\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?!\d)")


class ComposioPolicyDenied(RuntimeError):
    """A request failed one or more mandatory authorization checks."""


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _encryption_key() -> bytes:
    settings = get_settings()
    if not settings.secret_key or len(settings.secret_key) < 32:
        raise ComposioPolicyDenied("Segredo de criptografia do servidor ausente ou fraco.")
    if not settings.composio_identity_secret or len(settings.composio_identity_secret) < 32:
        raise ComposioPolicyDenied("COMPOSIO_IDENTITY_SECRET ausente ou fraco.")
    material = (
        b"mira-composio-approval-v1:"
        + settings.secret_key.encode("utf-8")
        + b":"
        + settings.composio_identity_secret.encode("utf-8")
    )
    return hashlib.sha256(material).digest()


def encrypt_arguments(*, tenant_id: str, arguments: dict[str, Any]) -> str:
    """AES-256-GCM envelope; tenant id is authenticated additional data."""
    payload = _canonical_json(arguments)
    if len(payload) > _MAX_ARGUMENT_BYTES:
        raise ComposioPolicyDenied("Argumentos excedem o limite permitido.")
    nonce = secrets.token_bytes(12)
    ciphertext = AESGCM(_encryption_key()).encrypt(
        nonce, payload, tenant_id.encode("utf-8")
    )
    envelope = b"v1." + nonce + ciphertext
    return base64.urlsafe_b64encode(envelope).decode("ascii")


def decrypt_arguments(*, tenant_id: str, ciphertext: str) -> dict[str, Any]:
    """Decrypt only inside trusted backend code; never expose this via an API."""
    try:
        envelope = base64.urlsafe_b64decode(ciphertext.encode("ascii"))
        if not envelope.startswith(b"v1.") or len(envelope) < 32:
            raise ValueError("invalid envelope")
        plaintext = AESGCM(_encryption_key()).decrypt(
            envelope[3:15], envelope[15:], tenant_id.encode("utf-8")
        )
        value = json.loads(plaintext.decode("utf-8"))
    except Exception as exc:
        raise ComposioPolicyDenied("Payload de aprovação inválido ou não autenticado.") from exc
    if not isinstance(value, dict):
        raise ComposioPolicyDenied("Argumentos devem ser um objeto JSON.")
    return value


def redact_arguments(value: Any, *, _depth: int = 0) -> Any:
    """Create a bounded, non-reversible preview for human approval screens."""
    if _depth > _MAX_DEPTH:
        return "[depth-limited]"
    if isinstance(value, dict):
        output = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= _MAX_ITEMS:
                output["_truncated"] = True
                break
            name = str(key)
            output[name] = "[redacted]" if _SENSITIVE_KEY.search(name) else redact_arguments(
                item, _depth=_depth + 1
            )
        return output
    if isinstance(value, list):
        return [
            redact_arguments(item, _depth=_depth + 1)
            for item in value[:_MAX_ITEMS]
        ] + (["[truncated]"] if len(value) > _MAX_ITEMS else [])
    if isinstance(value, str):
        if _EMAIL_VALUE.search(value) or _CPF_VALUE.search(value) or _PHONE_VALUE.search(value):
            return "[redacted]"
        return value[:500]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return "[unsupported]"


def _validate_schema_value(value: Any, schema: dict[str, Any], path: str = "arguments") -> None:
    """Conservative JSON-Schema subset; unknown schema constructs fail closed."""
    if not isinstance(schema, dict):
        raise ComposioPolicyDenied("Schema da ferramenta inválido.")
    allowed_keywords = {
        "type", "properties", "required", "additionalProperties", "enum",
        "items", "description", "title", "default", "minimum", "maximum",
        "minLength", "maxLength", "minItems", "maxItems",
    }
    if set(schema) - allowed_keywords:
        raise ComposioPolicyDenied("Schema contém regras não suportadas pelo validador seguro.")

    expected = schema.get("type")
    type_map = {
        "object": lambda v: isinstance(v, dict),
        "array": lambda v: isinstance(v, list),
        "string": lambda v: isinstance(v, str),
        "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
        "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
        "boolean": lambda v: isinstance(v, bool),
        "null": lambda v: v is None,
    }
    if expected not in type_map or not type_map[expected](value):
        raise ComposioPolicyDenied(f"Tipo inválido em {path}.")

    if "enum" in schema and value not in schema["enum"]:
        raise ComposioPolicyDenied(f"Valor fora do enum em {path}.")

    if expected == "object":
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        if not isinstance(properties, dict) or not isinstance(required, list):
            raise ComposioPolicyDenied("Schema de objeto inválido.")
        missing = [key for key in required if key not in value]
        if missing:
            raise ComposioPolicyDenied(f"Campos obrigatórios ausentes em {path}.")
        additional = schema.get("additionalProperties", True)
        unknown = set(value) - set(properties)
        if additional is False and unknown:
            raise ComposioPolicyDenied(f"Campos não permitidos em {path}.")
        if isinstance(additional, dict):
            for key in unknown:
                _validate_schema_value(value[key], additional, f"{path}.{key}")
        elif additional not in (True, False):
            raise ComposioPolicyDenied("Regra additionalProperties não suportada.")
        for key, item in value.items():
            if key in properties:
                _validate_schema_value(item, properties[key], f"{path}.{key}")
    elif expected == "array":
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", _MAX_ITEMS):
            raise ComposioPolicyDenied(f"Tamanho de lista inválido em {path}.")
        item_schema = schema.get("items")
        if not isinstance(item_schema, dict):
            raise ComposioPolicyDenied("Schema de lista sem definição de items.")
        for index, item in enumerate(value):
            _validate_schema_value(item, item_schema, f"{path}[{index}]")
    elif expected == "string":
        if len(value) < schema.get("minLength", 0) or len(value) > schema.get("maxLength", 10000):
            raise ComposioPolicyDenied(f"Comprimento inválido em {path}.")
    elif expected in {"integer", "number"}:
        if "minimum" in schema and value < schema["minimum"]:
            raise ComposioPolicyDenied(f"Valor abaixo do mínimo em {path}.")
        if "maximum" in schema and value > schema["maximum"]:
            raise ComposioPolicyDenied(f"Valor acima do máximo em {path}.")


def _tool_schema(toolkit_slug: str, tool_slug: str) -> dict[str, Any]:
    tools = list_tools_for_toolkit(toolkit_slug)
    match = next((item for item in tools if item.get("slug") == tool_slug.upper()), None)
    if not match:
        raise ComposioPolicyDenied("Ferramenta não existe no toolkit do catálogo atual.")
    schema = match.get("input_parameters")
    if isinstance(schema, dict) and "type" not in schema and isinstance(schema.get("parameters"), dict):
        schema = schema["parameters"]
    if not isinstance(schema, dict) or schema.get("type") != "object":
        raise ComposioPolicyDenied("Schema atual da ferramenta ausente ou incompatível.")
    return schema


async def authorize_tool_request(
    db: AsyncSession,
    *,
    auth: AuthContext,
    connected_account_id: str,
    toolkit_slug: str,
    tool_slug: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Resolve every authorization source from trusted server state."""
    if not auth.user_id or not auth.session_id or auth.aal < 2:
        raise ComposioPolicyDenied("Solicitação exige sessão humana AAL2.")
    settings = require_composio_configuration()
    if not settings.composio_tool_execution_enabled:
        # Requests may be staged for approval while execution remains disabled.
        pass
    toolkit = (toolkit_slug or "").strip().lower()
    tool = (tool_slug or "").strip().upper()
    account_id = (connected_account_id or "").strip()
    if not toolkit or not tool or not account_id:
        raise ComposioPolicyDenied("Toolkit, ferramenta e conta são obrigatórios.")
    if not composio_toolkit_allowed(toolkit, settings):
        raise ComposioPolicyDenied("Toolkit não está na allowlist global.")

    policy_result = await db.execute(
        select(TenantComposioToolkitPolicy).where(
            TenantComposioToolkitPolicy.tenant_id == auth.tenant_id,
            TenantComposioToolkitPolicy.toolkit_slug == toolkit,
        ).with_for_update()
    )
    policy = policy_result.scalar_one_or_none()
    if not policy or not policy.is_enabled or tool not in {
        str(item).upper() for item in (policy.tool_slugs or [])
    }:
        raise ComposioPolicyDenied("Ferramenta não está habilitada pela policy do tenant.")

    account_result = await db.execute(
        select(TenantComposioAccount).where(
            TenantComposioAccount.tenant_id == auth.tenant_id,
            TenantComposioAccount.connected_account_id == account_id,
            TenantComposioAccount.toolkit_slug == toolkit,
            TenantComposioAccount.status == "active",
        ).with_for_update()
    )
    account = account_result.scalar_one_or_none()
    if not account:
        raise ComposioPolicyDenied("Conta ativa não encontrada neste tenant/toolkit.")

    if not isinstance(arguments, dict):
        raise ComposioPolicyDenied("Argumentos devem ser um objeto JSON.")
    encoded = _canonical_json(arguments)
    if len(encoded) > _MAX_ARGUMENT_BYTES:
        raise ComposioPolicyDenied("Argumentos excedem o limite permitido.")
    schema = await run_in_threadpool(_tool_schema, toolkit, tool)
    _validate_schema_value(arguments, schema)
    fingerprint = hashlib.sha256(
        _canonical_json({
            "tenant_id": auth.tenant_id,
            "connected_account_id": account_id,
            "toolkit_slug": toolkit,
            "tool_slug": tool,
            "schema": schema,
            "arguments": arguments,
        })
    ).hexdigest()
    return {
        "tenant_id": auth.tenant_id,
        "requested_by_user_id": auth.user_id,
        "connected_account_id": account.connected_account_id,
        "toolkit_slug": toolkit,
        "tool_slug": tool,
        "arguments_ciphertext": encrypt_arguments(
            tenant_id=auth.tenant_id, arguments=arguments
        ),
        "arguments_preview": redact_arguments(arguments),
        "request_fingerprint": fingerprint,
    }
