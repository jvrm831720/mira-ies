"""Tenant-scoped outbound destination policy for connector endpoints.

This validates URL identity and configuration only. It does NOT resolve DNS,
pin addresses, or prevent DNS rebinding; those guarantees belong to the
connection transport and infrastructure egress controls (E2/E3).
"""
from __future__ import annotations

import ipaddress
import re
from collections.abc import Mapping
from urllib.parse import unquote, urlsplit


class DestinationPolicyError(ValueError):
    """Outbound destination is not explicitly authorized."""


_LOCAL_NAMES = frozenset({"localhost", "localhost.localdomain", "metadata.google.internal"})
_CONTROL = re.compile(r"[\x00-\x20\x7f]")


def _normalize_hostname(hostname: str) -> str:
    value = hostname.rstrip(".").lower()
    if not value or _CONTROL.search(value) or "%" in value:
        raise DestinationPolicyError("Hostname inválido.")
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        pass
    else:
        raise DestinationPolicyError("Endereço IP literal não é permitido como destino.")
    try:
        normalized = value.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise DestinationPolicyError("Hostname IDNA inválido.") from exc
    if normalized in _LOCAL_NAMES or normalized.endswith((".localhost", ".local", ".internal", ".test", ".invalid")):
        raise DestinationPolicyError("Hostname local ou reservado não é permitido.")
    if len(normalized) > 253 or any(\n        not label\n        or len(label) > 63\n        or not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", label)\n        for label in normalized.split(".")\n    ):
        raise DestinationPolicyError("Hostname inválido.")
    return normalized


def validate_tenant_destination(
    *,
    tenant_id: str,
    url: str,
    tenant_allowed_hosts: Mapping[str, frozenset[str] | set[str] | tuple[str, ...] | list[str]],
    allowed_ports: frozenset[int] | set[int] = frozenset({443}),
    allow_http: bool = False,
) -> str:
    """Return canonical URL only when its exact host is allowed for this tenant.

    No wildcard or suffix matching is supported. Callers must obtain the
    allowlist from trusted tenant configuration, never from request payloads.
    """
    if not isinstance(tenant_id, str) or not tenant_id.strip():
        raise DestinationPolicyError("tenant_id obrigatório.")
    if not isinstance(url, str) or not url or _CONTROL.search(url):
        raise DestinationPolicyError("URL de destino inválida.")
    try:
        parsed = urlsplit(url.strip())
        port = parsed.port
    except ValueError as exc:
        raise DestinationPolicyError("URL de destino inválida.") from exc
    expected_scheme = {"https"} | ({"http"} if allow_http else set())
    if (
        parsed.scheme.lower() not in expected_scheme
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or "\\" in parsed.path
        or any(segment in {".", ".."} for segment in parsed.path.split("/"))
    ):
        raise DestinationPolicyError("Destino deve ser uma URL HTTP(S) válida, sem credenciais, query ou fragmento.")
    host = _normalize_hostname(parsed.hostname)
    configured = tenant_allowed_hosts.get(tenant_id)
    if not configured:
        raise DestinationPolicyError("Tenant não possui allowlist explícita de destinos.")
    allowed = {_normalize_hostname(item) for item in configured}
    if host not in allowed:
        raise DestinationPolicyError("Hostname não autorizado para este tenant.")
    effective_port = port or (443 if parsed.scheme.lower() == "https" else 80)
    if effective_port not in allowed_ports:
        raise DestinationPolicyError("Porta de destino não autorizada.")
    netloc = host if port is None else f"{host}:{port}"
    return parsed._replace(scheme=parsed.scheme.lower(), netloc=netloc).geturl()
