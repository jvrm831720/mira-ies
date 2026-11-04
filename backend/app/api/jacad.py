"""Configuração, teste e sincronização sob demanda do conector JACAD."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthContext, require_min_role, _set_tenant_rls_context
from app.db.session import get_db
from app.models.jacad_connection import TenantJacadConnection
from app.services.jacad_queue import enqueue_jacad_sync, get_active_jacad_job, get_jacad_job, retry_jacad_sync
from app.services.connectors.tenant_destinations import authorize_tenant_destination
from app.services.connectors.jacad_api import (
    JacadApiClient,
    JacadConnectionError,
    decrypt_api_token,
    encrypt_api_token,
    validate_jacad_base_url,
)

router = APIRouter(prefix="/integrations/jacad", tags=["Integração JACAD"])


class JacadConfigurePayload(BaseModel):
    base_url: str = Field(min_length=10, max_length=255)
    api_token: str | None = Field(default=None, min_length=1, max_length=40)
    default_org_id: int | None = Field(default=None, ge=1)

    @field_validator("base_url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        return validate_jacad_base_url(value)


def _connection_response(connection: TenantJacadConnection) -> dict[str, Any]:
    return {
        "provider": "jacad",
        "configured": True,
        "enabled": connection.is_enabled,
        "base_url": connection.base_url,
        "default_org_id": connection.default_org_id,
        "status": connection.status,
        "last_tested_at": connection.last_tested_at.isoformat() if connection.last_tested_at else None,
        "last_sync_at": connection.last_sync_at.isoformat() if connection.last_sync_at else None,
        "last_sync_status": connection.last_sync_status,
        "last_sync_records": connection.last_sync_records,
        "last_error": connection.last_error,
        "credential_configured": bool(connection.encrypted_api_token),
    }


async def _get_connection(db: AsyncSession, tenant_id: str) -> TenantJacadConnection | None:
    result = await db.execute(
        select(TenantJacadConnection).where(TenantJacadConnection.tenant_id == tenant_id)
    )
    return result.scalar_one_or_none()


@router.get("")
async def get_jacad_connection(
    auth: AuthContext = Depends(require_min_role("coordinator")),
    db: AsyncSession = Depends(get_db),
):
    connection = await _get_connection(db, auth.tenant_id)
    if not connection:
        return {"provider": "jacad", "configured": False, "credential_configured": False}
    return _connection_response(connection)


@router.put("")
async def configure_jacad_connection(
    body: JacadConfigurePayload,
    auth: AuthContext = Depends(require_min_role("coordinator")),
    db: AsyncSession = Depends(get_db),
):
    connection = await _get_connection(db, auth.tenant_id)
    if connection:
        connection.base_url = body.base_url
        if body.api_token:
            connection.encrypted_api_token = encrypt_api_token(body.api_token)
        connection.default_org_id = body.default_org_id
        connection.is_enabled = True
        connection.status = "configured"
        connection.last_error = None
    else:
        if not body.api_token:
            raise HTTPException(status_code=422, detail="Informe o token JACAD na primeira configuração.")
        connection = TenantJacadConnection(
            tenant_id=auth.tenant_id,
            base_url=body.base_url,
            encrypted_api_token=encrypt_api_token(body.api_token),
            default_org_id=body.default_org_id,
        )
        db.add(connection)
    await db.commit()
    await _set_tenant_rls_context(db, auth.tenant_id)
    await db.refresh(connection)
    return _connection_response(connection)


@router.post("/test")
async def test_jacad_connection(
    auth: AuthContext = Depends(require_min_role("coordinator")),
    db: AsyncSession = Depends(get_db),
):
    connection = await _get_connection(db, auth.tenant_id)
    if not connection or not connection.is_enabled:
        raise HTTPException(status_code=404, detail="Configure a conexão JACAD antes de testar.")
    try:
        client = await JacadApiClient.for_tenant(
            db, tenant_id=auth.tenant_id, base_url=connection.base_url,
            api_token=decrypt_api_token(connection.encrypted_api_token),
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail="Destino JACAD não aprovado para este tenant.") from exc
    try:
        result = await client.test_connection(org_id=connection.default_org_id)
        connection.status = "connected"
        connection.last_tested_at = datetime.now(timezone.utc)
        connection.last_error = None
        await db.commit()
        return {"status": "connected", **result}
    except (JacadConnectionError, ValueError) as exc:
        connection.status = "error"
        connection.last_tested_at = datetime.now(timezone.utc)
        connection.last_error = str(exc)
        await db.commit()
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        await client.close()


@router.post("/sync", status_code=202)
async def sync_jacad_students(
    auth: AuthContext = Depends(require_min_role("coordinator")),
    db: AsyncSession = Depends(get_db),
):
    connection = await _get_connection(db, auth.tenant_id)
    if not connection or not connection.is_enabled:
        raise HTTPException(status_code=404, detail="Configure a conexão JACAD antes de sincronizar.")
    if connection.default_org_id is None:
        raise HTTPException(
            status_code=422,
            detail="Informe o ID da organização JACAD para sincronizar matrículas e dados financeiros.",
        )
    try:
        job = await enqueue_jacad_sync(tenant_id=auth.tenant_id, tenant_slug=auth.tenant_slug)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"status": job.get("status", "queued"), "job_id": job["id"],
            "deduplicated": bool(job.get("deduplicated")), "progress": job.get("progress")}


@router.get("/sync/current")
async def get_current_jacad_sync(
    auth: AuthContext = Depends(require_min_role("coordinator")),
):
    job = await get_active_jacad_job(tenant_id=auth.tenant_id)
    if not job:
        return None
    return {
        "job_id": job["id"], "status": job.get("status"),
        "progress": job.get("progress"), "result": job.get("result"),
        "last_error": job.get("last_error"), "attempt": job.get("attempt", 0),
        "created_at": job.get("created_at"), "updated_at": job.get("updated_at"),
    }


@router.get("/sync/{job_id}")
async def get_jacad_sync_status(
    job_id: str,
    auth: AuthContext = Depends(require_min_role("coordinator")),
):
    job = await get_jacad_job(job_id, tenant_id=auth.tenant_id)
    if not job:
        raise HTTPException(status_code=404, detail="Sincronização JACAD não encontrada.")
    return {
        "job_id": job["id"], "status": job.get("status"),
        "progress": job.get("progress"), "result": job.get("result"),
        "last_error": job.get("last_error"),
        "attempt": job.get("attempt", 0),
        "created_at": job.get("created_at"),
        "updated_at": job.get("updated_at"),
    }


@router.post("/sync/{job_id}/retry", status_code=202)
async def retry_jacad_sync_route(
    job_id: str,
    auth: AuthContext = Depends(require_min_role("coordinator")),
):
    try:
        job = await retry_jacad_sync(job_id, tenant_id=auth.tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not job:
        raise HTTPException(status_code=404, detail="Sincronização JACAD não encontrada.")
    return {"job_id": job["id"], "status": job.get("status"), "progress": job.get("progress")}
