"""Institutional document attestation and minimal public integrity verification."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.native_academic import PortalIdentity, _portal_identity, _require_ies
from app.core.auth import AuthContext, require_permission
from app.db.session import get_db
from app.models.student_document_attestation import StudentDocumentAttestation
from app.models.student_services import StudentDocument
from app.services.student_document_attestation import (
    AttestationDenied, parse_code, sign_document, signing_keys, verification_code, verify_code,
)

institution_router = APIRouter(prefix="/native-academic/documents", tags=["Document provenance"])
portal_router = APIRouter(prefix="/student-portal/services/documents", tags=["Student document provenance"])
public_router = APIRouter(prefix="/public/academic-documents", tags=["Document integrity verification"])


def _staff_aal2(auth: AuthContext):
    if not auth.user_id or not auth.session_id or auth.aal < 2:
        raise HTTPException(status_code=403, detail="Emissão documental exige sessão institucional MFA AAL2.")


@institution_router.post("/{document_id}/attest", status_code=201)
async def attest_document(
    document_id: UUID,
    auth: AuthContext = Depends(require_permission("critical.manage")),
    db: AsyncSession = Depends(get_db),
):
    _staff_aal2(auth)
    await _require_ies(db, auth)
    try:
        key_id, keys = signing_keys()
    except AttestationDenied as exc:
        raise HTTPException(status_code=503, detail="Emissão verificável não configurada.") from exc
    row = (await db.execute(select(StudentDocument).where(
        StudentDocument.id == str(document_id),
        StudentDocument.tenant_id == auth.tenant_id,
    ).with_for_update())).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")
    if row.publication_status != "published":
        raise HTTPException(status_code=409, detail="Documento deve ser publicado antes da emissão.")
    prior = (await db.execute(select(StudentDocumentAttestation).where(
        StudentDocumentAttestation.tenant_id == auth.tenant_id,
        StudentDocumentAttestation.document_id == row.id,
    ))).scalar_one_or_none()
    if prior:
        raise HTTPException(status_code=409, detail="Documento já possui emissão; reemissão exige novo documento.")
    try:
        digest, signature = sign_document(row, keys[key_id])
    except AttestationDenied as exc:
        raise HTTPException(status_code=409, detail="Conteúdo documental inválido.") from exc
    attestation = StudentDocumentAttestation(
        tenant_id=auth.tenant_id, document_id=row.id, student_id=row.student_id,
        issued_by_user_id=auth.user_id, signing_key_id=key_id,
        content_digest=digest, signature=signature,
        issued_at=datetime.now(timezone.utc),
    )
    db.add(attestation)
    await db.flush()
    code = verification_code(attestation, keys[key_id])
    await db.commit()
    return {"document_id": row.id, "attestation_id": attestation.id,
            "verification_code": code, "content_digest": digest,
            "proof_type": "mira_hmac_integrity", "qualified_signature": False}


@institution_router.post("/{document_id}/revoke")
async def revoke_document(
    document_id: UUID,
    auth: AuthContext = Depends(require_permission("critical.manage")),
    db: AsyncSession = Depends(get_db),
):
    _staff_aal2(auth)
    await _require_ies(db, auth)
    try:
        signing_keys()
    except AttestationDenied as exc:
        raise HTTPException(status_code=503, detail="Verificação documental indisponível.") from exc
    item = (await db.execute(select(StudentDocumentAttestation).where(
        StudentDocumentAttestation.tenant_id == auth.tenant_id,
        StudentDocumentAttestation.document_id == str(document_id),
    ).with_for_update())).scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Emissão não encontrada.")
    if item.revoked_at is not None:
        raise HTTPException(status_code=409, detail="Emissão já revogada.")
    item.revoked_at = datetime.now(timezone.utc)
    item.revoked_by_user_id = auth.user_id
    await db.commit()
    return {"document_id": str(document_id), "valid": False, "revoked": True}


@portal_router.get("/{document_id}/proof")
async def student_document_proof(
    document_id: UUID,
    identity: PortalIdentity = Depends(_portal_identity),
    db: AsyncSession = Depends(get_db),
):
    try:
        _, keys = signing_keys()
    except AttestationDenied as exc:
        raise HTTPException(status_code=503, detail="Verificação documental em homologação.") from exc
    row = (await db.execute(select(StudentDocument).where(
        StudentDocument.tenant_id == identity.tenant_id,
        StudentDocument.student_id == identity.student.id,
        StudentDocument.id == str(document_id),
        StudentDocument.publication_status == "published",
    ))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")
    item = (await db.execute(select(StudentDocumentAttestation).where(
        StudentDocumentAttestation.tenant_id == identity.tenant_id,
        StudentDocumentAttestation.student_id == identity.student.id,
        StudentDocumentAttestation.document_id == row.id,
        StudentDocumentAttestation.revoked_at.is_(None),
    ))).scalar_one_or_none()
    if item is None or item.signing_key_id not in keys:
        raise HTTPException(status_code=404, detail="Comprovante não disponível.")
    valid = verify_code(verification_code(item, keys[item.signing_key_id]), item, row)
    if not valid:
        raise HTTPException(status_code=409, detail="Integridade documental não confirmada.")
    return {"document_id": row.id, "verification_code": verification_code(item, keys[item.signing_key_id]),
            "content_digest": item.content_digest, "qualified_signature": False}


class VerificationInput(BaseModel):
    code: str = Field(min_length=138, max_length=138)


@public_router.post("/verify")
async def public_verify(
    body: VerificationInput, response: Response, db: AsyncSession = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"
    try:
        tenant_id, attestation_id, _ = parse_code(body.code)
        signing_keys()
    except AttestationDenied:
        return {"valid": False}
    # RLS remains effective, even for public verification, using the tenant UUID
    # embedded in the high-entropy proof; no arbitrary caller-supplied tenant ID.
    await db.execute(text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": tenant_id})
    item = (await db.execute(select(StudentDocumentAttestation).where(
        StudentDocumentAttestation.tenant_id == tenant_id,
        StudentDocumentAttestation.id == attestation_id,
    ))).scalar_one_or_none()
    if item is None:
        return {"valid": False}
    row = (await db.execute(select(StudentDocument).where(
        StudentDocument.tenant_id == tenant_id,
        StudentDocument.student_id == item.student_id,
        StudentDocument.id == item.document_id,
    ))).scalar_one_or_none()
    return {"valid": bool(row and verify_code(body.code, item, row))}
