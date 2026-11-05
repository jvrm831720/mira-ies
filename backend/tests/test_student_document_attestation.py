"""Wave 4 document integrity proof tests. HMAC is not a qualified signature."""
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services import student_document_attestation as att


def document():
    return SimpleNamespace(
        id=str(uuid4()), tenant_id=str(uuid4()), student_id=str(uuid4()),
        kind="declaration", title="Declaração de matrícula",
        content_text="Registro institucional de teste",
        published_at=datetime(2026, 11, 5, 21, 0, tzinfo=timezone.utc),
        publication_status="published",
    )


def configure(monkeypatch):
    monkeypatch.setattr(att, "get_settings", lambda: SimpleNamespace(
        student_document_attestation_enabled=True,
        student_document_signing_keys='{"key_1":"' + "k" * 48 + '"}',
        student_document_active_key_id="key_1",
    ))


def attestation(doc, key):
    digest, signature = att.sign_document(doc, key)
    return SimpleNamespace(
        id=str(uuid4()), tenant_id=doc.tenant_id, student_id=doc.student_id,
        document_id=doc.id, signing_key_id="key_1", content_digest=digest,
        signature=signature, revoked_at=None,
    )


def test_hmac_proof_survives_canonicalization_and_rejects_tamper(monkeypatch):
    configure(monkeypatch)
    doc = document()
    item = attestation(doc, b"k" * 48)
    code = att.verification_code(item, b"k" * 48)
    assert len(code) == 138
    assert att.verify_code(code, item, doc)
    doc.content_text += " alterado"
    assert not att.verify_code(code, item, doc)


def test_revoked_proof_and_wrong_student_are_invalid(monkeypatch):
    configure(monkeypatch)
    doc = document()
    item = attestation(doc, b"k" * 48)
    code = att.verification_code(item, b"k" * 48)
    item.student_id = str(uuid4())
    assert not att.verify_code(code, item, doc)
    item.student_id = doc.student_id
    item.revoked_at = datetime.now(timezone.utc)
    assert not att.verify_code(code, item, doc)


def test_code_rejects_malformed_and_forged_mac(monkeypatch):
    configure(monkeypatch)
    doc = document()
    item = attestation(doc, b"k" * 48)
    code = att.verification_code(item, b"k" * 48)
    assert not att.verify_code(code[:-1] + ("0" if code[-1] != "0" else "1"), item, doc)
    with pytest.raises(att.AttestationDenied):
        att.parse_code("not-a-proof")


def test_missing_key_fails_closed(monkeypatch):
    monkeypatch.setattr(att, "get_settings", lambda: SimpleNamespace(
        student_document_attestation_enabled=False,
        student_document_signing_keys="",
        student_document_active_key_id="",
    ))
    with pytest.raises(att.AttestationDenied):
        att.signing_keys()


def test_documents_require_published_at():
    doc = document()
    doc.published_at = None
    with pytest.raises(att.AttestationDenied):
        att.canonical(doc)
