"""MIRA institutional document provenance (HMAC; not a qualified digital signature)."""
from __future__ import annotations

import hashlib
import hmac
import json
import re
from datetime import timezone
from uuid import UUID

from app.core.config import get_settings

_KEY_ID = re.compile(r"^[a-zA-Z0-9_-]{1,40}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")


class AttestationDenied(ValueError):
    pass


def signing_keys() -> tuple[str, dict[str, bytes]]:
    settings = get_settings()
    if not settings.student_document_attestation_enabled:
        raise AttestationDenied("Emissão verificável desabilitada.")
    try:
        raw = json.loads(settings.student_document_signing_keys or "{}")
    except (ValueError, TypeError) as exc:
        raise AttestationDenied("Configuração das chaves inválida.") from exc
    if not isinstance(raw, dict) or not 1 <= len(raw) <= 8:
        raise AttestationDenied("Não há chave institucional de assinatura configurada.")
    keys = {}
    for name, value in raw.items():
        if not isinstance(name, str) or not _KEY_ID.fullmatch(name):
            raise AttestationDenied("Identificador de chave inválido.")
        if not isinstance(value, str) or len(value.encode()) < 32:
            raise AttestationDenied("Chave de autenticação precisa de no mínimo 32 bytes.")
        keys[name] = value.encode()
    active = settings.student_document_active_key_id
    if not active or active not in keys:
        raise AttestationDenied("Chave ativa ausente.")
    return active, keys


def canonical(doc) -> bytes:
    if doc.published_at is None:
        raise AttestationDenied("Documento ainda não foi publicado.")
    instant = doc.published_at
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise AttestationDenied("Publicação sem horário inequívoco.")
    instant = instant.astimezone(timezone.utc)
    return json.dumps({
        "schema": "mira_student_document_v1",
        "tenant_id": str(doc.tenant_id),
        "document_id": str(doc.id),
        "student_id": str(doc.student_id),
        "kind": doc.kind,
        "title": doc.title,
        "content_text": doc.content_text,
        "published_at": instant.isoformat(),
    }, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def sign_document(doc, key: bytes) -> tuple[str, str]:
    payload = canonical(doc)
    digest = hashlib.sha256(payload).hexdigest()
    mac = hmac.new(key, b"mira:doc:v1:" + bytes.fromhex(digest), hashlib.sha256).hexdigest()
    return digest, mac


def verification_code(attestation, key: bytes) -> str:
    claim = f"{UUID(str(attestation.tenant_id))}.{UUID(str(attestation.id))}"
    mac = hmac.new(key, ("mira:proof:v1:" + claim).encode(), hashlib.sha256).hexdigest()
    return f"{claim}.{mac}"


def parse_code(code: str) -> tuple[str, str, str]:
    if not isinstance(code, str) or len(code) != 138:
        raise AttestationDenied("Código inválido.")
    pieces = code.split(".")
    if len(pieces) != 3 or not _DIGEST.fullmatch(pieces[2]):
        raise AttestationDenied("Código inválido.")
    try:
        tenant = str(UUID(pieces[0]))
        attestation = str(UUID(pieces[1]))
    except (ValueError, TypeError) as exc:
        raise AttestationDenied("Código inválido.") from exc
    if code != f"{tenant}.{attestation}.{pieces[2]}":
        raise AttestationDenied("Código inválido.")
    return tenant, attestation, pieces[2]


def verify_code(code: str, attestation, doc) -> bool:
    try:
        tenant, reference, supplied = parse_code(code)
        _, keys = signing_keys()
        if tenant != str(attestation.tenant_id) or reference != str(attestation.id):
            return False
        if (attestation.revoked_at is not None
                or doc.publication_status != "published"
                or str(doc.tenant_id) != tenant
                or str(doc.student_id) != str(attestation.student_id)
                or str(doc.id) != str(attestation.document_id)):
            return False
        key = keys.get(attestation.signing_key_id)
        if key is None:
            return False
        digest, signature = sign_document(doc, key)
        return (hmac.compare_digest(digest, attestation.content_digest)
                and hmac.compare_digest(signature, attestation.signature)
                and hmac.compare_digest(
                    verification_code(attestation, key).rsplit(".", 1)[-1],
                    supplied,
                ))
    except (AttestationDenied, ValueError, TypeError, AttributeError):
        return False
