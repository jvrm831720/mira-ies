"""Tenant-scoped Frappe Education integration (read-only, disabled by default)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthContext, require_permission
from app.core.config import get_settings
from app.db.session import get_db
from app.models.frappe_connection import TenantFrappeConnection, TenantFrappeStudentLink
from app.models.student import Student
from app.services.connectors.destination_policy import DestinationPolicyError, normalize_hostname
from app.services.connectors.frappe_education_api import FrappeApiError, FrappeEducationClient
from app.services.connectors.frappe_secrets import (
    FrappeSecretError, decrypt_frappe_secret, encrypt_frappe_secret,
)
from app.services.connectors.tenant_destinations import authorize_tenant_destination

router = APIRouter(prefix="/integrations/frappe-ies", tags=["Frappe Education"])


class FrappeConnectionPayload(BaseModel):
    hostname: str = Field(min_length=4, max_length=253)
    api_key: str = Field(min_length=8, max_length=255)
    api_secret: str = Field(min_length=8, max_length=2048)

    @field_validator("hostname")
    @classmethod
    def validate_hostname(cls, value: str) -> str:
        return normalize_hostname(value)

    @field_validator("api_key", "api_secret")
    @classmethod
    def validate_token(cls, value: str) -> str:
        if any(ord(char) < 33 or ord(char) == 127 for char in value):
            raise ValueError("Credencial inválida.")
        return value


class FrappeStudentLinkPayload(BaseModel):
    student_id: UUID
    frappe_student_name: str = Field(min_length=1, max_length=180)

    @field_validator("frappe_student_name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if value != value.strip() or any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError("Identificador Frappe inválido.")
        return value


def _require_enabled() -> None:
    if not get_settings().frappe_ies_enabled:
        raise HTTPException(
            status_code=503,
            detail="Frappe Education desativado no ambiente. Requer homologação e FRAPPE_IES_ENABLED=true.",
        )


def _response(row: TenantFrappeConnection | None) -> dict[str, Any]:
    if not row:
        return {"provider": "frappe_ies", "configured": False, "enabled": False}
    return {
        "provider": "frappe_ies", "configured": True, "enabled": row.is_enabled,
        "hostname": row.hostname, "status": row.status,
        "last_checked_at": row.last_checked_at.isoformat() if row.last_checked_at else None,
        "last_error_code": row.last_error_code,
        "capabilities": {
            "student_profile": "read_only",
            "attendance": "read_only",
            "grades": "read_only",
            "invoices": "read_only_unreconciled",
            "payments": "not_implemented",
            "settlements": "not_implemented",
            "document_downloads": "not_implemented",
            "student_portal": "not_implemented",
            "data_import": "not_implemented",
        },
    }


async def _connection(db: AsyncSession, tenant_id: str) -> TenantFrappeConnection | None:
    row = await db.execute(select(TenantFrappeConnection).where(
        TenantFrappeConnection.tenant_id == tenant_id
    ))
    return row.scalar_one_or_none()


async def _client(
    db: AsyncSession, tenant_id: str, *, require_verified: bool = True,
) -> tuple[TenantFrappeConnection, FrappeEducationClient]:
    _require_enabled()
    row = await _connection(db, tenant_id)
    if not row or (require_verified and (not row.is_enabled or row.status != "verified")):
        raise HTTPException(status_code=404, detail="Conexão Frappe não habilitada para esta IES.")
    try:
        client = await FrappeEducationClient.for_tenant(
            db, tenant_id=tenant_id, hostname=row.hostname,
            api_key=decrypt_frappe_secret(row.encrypted_api_key),
            api_secret=decrypt_frappe_secret(row.encrypted_api_secret),
        )
    except DestinationPolicyError as exc:
        raise HTTPException(status_code=403, detail="Destino Frappe sem aprovação vigente.") from exc
    except FrappeSecretError as exc:
        raise HTTPException(status_code=503, detail="Credenciais Frappe indisponíveis.") from exc
    return row, client


def _upstream_error(exc: FrappeApiError) -> HTTPException:
    # Never include upstream content, tokens, private URLs or student documents.
    return HTTPException(
        status_code=503 if exc.code in {"transport_error", "upstream_unavailable"} else 502,
        detail="Falha na consulta à origem Frappe (" + exc.code + ").",
    )


@router.get("/connection")
async def get_connection(
    auth: AuthContext = Depends(require_permission("settings.manage")),
    db: AsyncSession = Depends(get_db),
):
    return _response(await _connection(db, auth.tenant_id))


@router.put("/connection")
async def put_connection(
    body: FrappeConnectionPayload,
    auth: AuthContext = Depends(require_permission("settings.manage")),
    db: AsyncSession = Depends(get_db),
):
    # First approve exactly this host in /security/connector-destinations
    # with connector_key=frappe_ies; no URL is user-supplied to the HTTP client.
    try:
        await authorize_tenant_destination(
            db, tenant_id=auth.tenant_id, connector_key="frappe_ies",
            url="https://" + body.hostname,
        )
    except DestinationPolicyError as exc:
        raise HTTPException(status_code=422, detail="Aprove primeiro o hostname Frappe para esta IES.") from exc
    row = await _connection(db, auth.tenant_id)
    try:
        encrypted_key = encrypt_frappe_secret(body.api_key)
        encrypted_secret = encrypt_frappe_secret(body.api_secret)
    except FrappeSecretError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if row:
        row.hostname = body.hostname
        row.encrypted_api_key = encrypted_key
        row.encrypted_api_secret = encrypted_secret
        row.is_enabled = False
        row.status = "configured"
        row.last_error_code = None
        row.last_checked_at = None
        row.updated_at = datetime.now(timezone.utc)
    else:
        row = TenantFrappeConnection(
            tenant_id=auth.tenant_id, hostname=body.hostname,
            encrypted_api_key=encrypted_key, encrypted_api_secret=encrypted_secret,
        )
        db.add(row)
    await db.commit()
    return _response(row)


@router.post("/connection/test")
async def test_connection(
    auth: AuthContext = Depends(require_permission("settings.manage")),
    db: AsyncSession = Depends(get_db),
):
    row, client = await _client(db, auth.tenant_id, require_verified=False)
    try:
        ok = await client.test_connection()
        if not ok:
            raise FrappeApiError("unexpected_auth_response")
        row.status = "verified"
        row.is_enabled = True
        row.last_error_code = None
        await db.commit()
        return _response(row)
    except FrappeApiError as exc:
        row.status = "error"
        row.is_enabled = False
        row.last_error_code = exc.code[:40]
        await db.commit()
        raise _upstream_error(exc) from exc
    finally:
        row.last_checked_at = datetime.now(timezone.utc)
        await client.close()
        await db.commit()


@router.delete("/connection")
async def disable_connection(
    auth: AuthContext = Depends(require_permission("settings.manage")),
    db: AsyncSession = Depends(get_db),
):
    row = await _connection(db, auth.tenant_id)
    if not row:
        raise HTTPException(status_code=404, detail="Conexão Frappe inexistente.")
    row.is_enabled = False
    row.status = "disabled"
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return _response(row)


@router.put("/student-links")
async def link_student(
    body: FrappeStudentLinkPayload,
    auth: AuthContext = Depends(require_permission("settings.manage")),
    db: AsyncSession = Depends(get_db),
):
    student_id = str(body.student_id)
    local = await db.execute(select(Student.id).where(
        Student.id == student_id, Student.tenant_id == auth.tenant_id
    ))
    if local.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Aluno não encontrado nesta IES.")
    _row, client = await _client(db, auth.tenant_id)
    try:
        await client.get_student(body.frappe_student_name)
    except FrappeApiError as exc:
        raise _upstream_error(exc) from exc
    finally:
        await client.close()
    found = await db.execute(select(TenantFrappeStudentLink).where(
        TenantFrappeStudentLink.tenant_id == auth.tenant_id,
        TenantFrappeStudentLink.student_id == student_id,
    ))
    link = found.scalar_one_or_none()
    if link:
        link.frappe_student_name = body.frappe_student_name
        link.updated_at = datetime.now(timezone.utc)
    else:
        db.add(TenantFrappeStudentLink(
            tenant_id=auth.tenant_id, student_id=student_id,
            frappe_student_name=body.frappe_student_name,
        ))
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Identificador Frappe já vinculado a outro aluno.") from exc
    return {"student_id": student_id, "linked": True, "provider": "frappe_ies"}


async def _verified_link(db: AsyncSession, tenant_id: str, student_id: str) -> TenantFrappeStudentLink:
    try:
        student_uuid = str(UUID(student_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Aluno não encontrado.") from exc
    local = await db.execute(select(Student.id).where(
        Student.id == student_uuid, Student.tenant_id == tenant_id
    ))
    if local.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Aluno não encontrado.")
    result = await db.execute(select(TenantFrappeStudentLink).where(
        TenantFrappeStudentLink.student_id == student_uuid,
        TenantFrappeStudentLink.tenant_id == tenant_id,
    ))
    link = result.scalar_one_or_none()
    if link is None:
        raise HTTPException(status_code=404, detail="Aluno ainda não vinculado ao Frappe.")
    return link


@router.get("/students/{student_id}/profile")
async def student_profile(
    student_id: str,
    auth: AuthContext = Depends(require_permission("students.sensitive.view")),
    db: AsyncSession = Depends(get_db),
):
    link = await _verified_link(db, auth.tenant_id, student_id)
    _row, client = await _client(db, auth.tenant_id)
    try:
        record = await client.get_student(link.frappe_student_name)
        return {"student_id": link.student_id, "source": "frappe", "profile": record}
    except FrappeApiError as exc:
        raise _upstream_error(exc) from exc
    finally:
        await client.close()


@router.get("/students/{student_id}/{resource}")
async def student_resource(
    student_id: str,
    resource: str,
    offset: int = Query(default=0, ge=0, le=10000),
    limit: int = Query(default=30, ge=1, le=100),
    auth: AuthContext = Depends(require_permission("students.sensitive.view")),
    db: AsyncSession = Depends(get_db),
):
    doctypes = {
        "attendance": "Student Attendance",
        "grades": "Assessment Result",
        "invoices": "Sales Invoice",
    }
    if resource not in doctypes:
        raise HTTPException(status_code=404, detail="Recurso Frappe não disponível.")
    link = await _verified_link(db, auth.tenant_id, student_id)
    _row, client = await _client(db, auth.tenant_id)
    try:
        result = await client.list_for_student(
            doctypes[resource], link.frappe_student_name, offset=offset, limit=limit,
        )
        return {"student_id": link.student_id, "resource": resource, **result}
    except FrappeApiError as exc:
        raise _upstream_error(exc) from exc
    finally:
        await client.close()
