"""Tenant-scoped configuration and known-student reads for SophiA."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthContext, require_min_role, _set_tenant_rls_context
from app.db.session import get_db
from app.models.sophia_connection import TenantSophiaConnection, TenantSophiaStudentLink
from app.models.student import Student
from app.services.connectors.sophia_api import SophiaApiClient, SophiaApiConfig, SophiaApiError
from app.services.connectors.sophia_secrets import decrypt_sophia_secret, encrypt_sophia_secret

router = APIRouter(prefix="/integrations/sophia", tags=["Integração SophiA"])


class SophiaConfigurePayload(BaseModel):
    base_url: str = Field(min_length=12, max_length=500)
    username: str | None = Field(default=None, min_length=1, max_length=255)
    password: str | None = Field(default=None, min_length=1, max_length=255)


class SophiaStudentLinkPayload(BaseModel):
    codigo_interno: int = Field(gt=0)


def _connection_response(connection: TenantSophiaConnection) -> dict[str, Any]:
    return {
        "provider": "sophia",
        "configured": True,
        "enabled": connection.is_enabled,
        "base_url": connection.base_url,
        "status": connection.status,
        "last_tested_at": connection.last_tested_at.isoformat() if connection.last_tested_at else None,
        "last_error": connection.last_error,
        "credential_configured": bool(connection.encrypted_username and connection.encrypted_password),
    }


async def _get_connection(db: AsyncSession, tenant_id: str) -> TenantSophiaConnection | None:
    result = await db.execute(
        select(TenantSophiaConnection).where(TenantSophiaConnection.tenant_id == tenant_id)
    )
    return result.scalar_one_or_none()


async def _client_for_tenant(db: AsyncSession, tenant_id: str) -> SophiaApiClient:
    connection = await _get_connection(db, tenant_id)
    if not connection or not connection.is_enabled:
        raise HTTPException(status_code=404, detail="Configure a conexão SophiA antes de consultar.")
    config = SophiaApiConfig(
        base_url=connection.base_url,
        username=decrypt_sophia_secret(connection.encrypted_username),
        password=decrypt_sophia_secret(connection.encrypted_password),
    )
    return SophiaApiClient(config)


async def _student_code(db: AsyncSession, tenant_id: str, student_id: str) -> int:
    student_result = await db.execute(
        select(Student.id).where(Student.id == student_id, Student.tenant_id == tenant_id)
    )
    if student_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Aluno não encontrado neste tenant.")
    link_result = await db.execute(
        select(TenantSophiaStudentLink).where(
            TenantSophiaStudentLink.tenant_id == tenant_id,
            TenantSophiaStudentLink.student_id == student_id,
        )
    )
    link = link_result.scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=409, detail="Aluno ainda não possui CodigoInterno SophiA vinculado.")
    return link.codigo_interno


@router.get("")
async def get_sophia_connection(
    auth: AuthContext = Depends(require_min_role("coordinator")),
    db: AsyncSession = Depends(get_db),
):
    connection = await _get_connection(db, auth.tenant_id)
    if not connection:
        return {"provider": "sophia", "configured": False, "credential_configured": False}
    return _connection_response(connection)


@router.put("")
async def configure_sophia_connection(
    body: SophiaConfigurePayload,
    auth: AuthContext = Depends(require_min_role("coordinator")),
    db: AsyncSession = Depends(get_db),
):
    try:
        # Validate URL and required credential fields before persisting anything.
        SophiaApiConfig(
            base_url=body.base_url, username=body.username or "validation",
            password=body.password or "validation",
        ).validated_base_url()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    connection = await _get_connection(db, auth.tenant_id)
    if not connection and (not body.username or not body.password):
        raise HTTPException(status_code=422, detail="Informe usuário e senha na primeira configuração.")
    if connection and body.base_url.rstrip("/") != connection.base_url.rstrip("/") and (
        not body.username or not body.password
    ):
        raise HTTPException(status_code=422, detail="Informe usuário e senha ao alterar a URL da instalação.")
    if connection:
        connection.base_url = body.base_url.rstrip("/")
        if body.username:
            connection.encrypted_username = encrypt_sophia_secret(body.username)
        if body.password:
            connection.encrypted_password = encrypt_sophia_secret(body.password)
        connection.is_enabled = True
        connection.status = "configured"
        connection.last_error = None
    else:
        connection = TenantSophiaConnection(
            tenant_id=auth.tenant_id,
            base_url=body.base_url.rstrip("/"),
            encrypted_username=encrypt_sophia_secret(body.username or ""),
            encrypted_password=encrypt_sophia_secret(body.password or ""),
        )
        db.add(connection)
    await db.commit()
    await _set_tenant_rls_context(db, auth.tenant_id)
    await db.refresh(connection)
    return _connection_response(connection)


@router.post("/test")
async def test_sophia_connection(
    auth: AuthContext = Depends(require_min_role("coordinator")),
    db: AsyncSession = Depends(get_db),
):
    connection = await _get_connection(db, auth.tenant_id)
    if not connection or not connection.is_enabled:
        raise HTTPException(status_code=404, detail="Configure a conexão SophiA antes de testar.")
    client = await _client_for_tenant(db, auth.tenant_id)
    try:
        units = await client.get_units()
        courses = await client.get_courses()
        connection.status = "connected"
        connection.last_tested_at = datetime.now(timezone.utc)
        connection.last_error = None
        await db.commit()
        return {"status": "connected", "units_sampled": len(units), "courses_sampled": len(courses)}
    except (SophiaApiError, ValueError) as exc:
        connection.status = "error"
        connection.last_tested_at = datetime.now(timezone.utc)
        connection.last_error = str(exc)[:500]
        await db.commit()
        raise HTTPException(status_code=502, detail="Falha ao validar a conexão SophiA.") from exc
    finally:
        await client.close()


@router.put("/students/{student_id}/mapping")
async def link_sophia_student(
    student_id: str,
    body: SophiaStudentLinkPayload,
    auth: AuthContext = Depends(require_min_role("coordinator")),
    db: AsyncSession = Depends(get_db),
):
    student_result = await db.execute(
        select(Student).where(Student.id == student_id, Student.tenant_id == auth.tenant_id)
    )
    if not student_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Aluno não encontrado neste tenant.")
    duplicate = await db.execute(
        select(TenantSophiaStudentLink).where(
            TenantSophiaStudentLink.tenant_id == auth.tenant_id,
            TenantSophiaStudentLink.codigo_interno == body.codigo_interno,
            TenantSophiaStudentLink.student_id != student_id,
        )
    )
    if duplicate.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="CodigoInterno já está vinculado a outro aluno deste tenant.")
    result = await db.execute(
        select(TenantSophiaStudentLink).where(
            TenantSophiaStudentLink.tenant_id == auth.tenant_id,
            TenantSophiaStudentLink.student_id == student_id,
        )
    )
    link = result.scalar_one_or_none()
    if link:
        link.codigo_interno = body.codigo_interno
    else:
        link = TenantSophiaStudentLink(
            tenant_id=auth.tenant_id, student_id=student_id,
            codigo_interno=body.codigo_interno, created_by_user_id=auth.user_id,
        )
        db.add(link)
    await db.commit()
    return {"student_id": student_id, "codigo_interno": link.codigo_interno, "linked": True}


async def _read_student_resource(
    resource: str, student_id: str, auth: AuthContext, db: AsyncSession
) -> list[dict[str, Any]]:
    codigo = await _student_code(db, auth.tenant_id, student_id)
    client = await _client_for_tenant(db, auth.tenant_id)
    try:
        if resource == "finance":
            return await client.get_student_finance(codigo)
        if resource == "report-card":
            return await client.get_student_report_card(codigo)
        if resource == "recent-grades":
            return await client.get_student_recent_grades(codigo)
        raise HTTPException(status_code=404, detail="Recurso SophiA não permitido.")
    except SophiaApiError as exc:
        raise HTTPException(status_code=502, detail="Falha na consulta ao SophiA.") from exc
    finally:
        await client.close()


@router.get("/students/{student_id}/finance")
async def get_sophia_student_finance(
    student_id: str, auth: AuthContext = Depends(require_min_role("coordinator")),
    db: AsyncSession = Depends(get_db),
):
    return await _read_student_resource("finance", student_id, auth, db)


@router.get("/students/{student_id}/report-card")
async def get_sophia_student_report_card(
    student_id: str, auth: AuthContext = Depends(require_min_role("coordinator")),
    db: AsyncSession = Depends(get_db),
):
    return await _read_student_resource("report-card", student_id, auth, db)


@router.get("/students/{student_id}/recent-grades")
async def get_sophia_student_recent_grades(
    student_id: str, auth: AuthContext = Depends(require_min_role("coordinator")),
    db: AsyncSession = Depends(get_db),
):
    return await _read_student_resource("recent-grades", student_id, auth, db)

@router.get("/students/{student_id}/finance/{id_titulo}/boleto")
async def get_sophia_student_boleto(
    student_id: str, id_titulo: int,
    auth: AuthContext = Depends(require_min_role("coordinator")),
    db: AsyncSession = Depends(get_db),
):
    await _student_code(db, auth.tenant_id, student_id)
    client = await _client_for_tenant(db, auth.tenant_id)
    try:
        return await client.get_student_boleto(id_titulo)
    except (SophiaApiError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="Falha na consulta do boleto SophiA.") from exc
    finally:
        await client.close()
