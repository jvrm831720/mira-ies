"""Tenant configuration and job endpoints for the Sponte BI connector."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthContext, require_min_role, _set_tenant_rls_context
from app.db.session import get_db
from app.models.sponte_connection import TenantSponteConnection
from app.services.connectors.jacad_api import decrypt_api_token, encrypt_api_token
from app.services.connectors.sponte_api import SponteApiClient, SponteConnectionError
from app.services.sponte_queue import (
    enqueue_sponte_sync, get_current_sponte_job, get_sponte_job, retry_sponte_sync,
)

router = APIRouter(prefix="/integrations/sponte", tags=["Integração Sponte BI"])


class SponteConfigurePayload(BaseModel):
    api_key: str | None = Field(default=None, min_length=1, max_length=512)
    client_code: int = Field(ge=1)
    initial_extraction_date: date = Field(default=date(2025, 1, 1))


def _connection_response(connection: TenantSponteConnection) -> dict[str, Any]:
    return {
        "provider": "sponte",
        "configured": True,
        "enabled": connection.is_enabled,
        "client_code": connection.client_code,
        "initial_extraction_date": connection.initial_extraction_date.isoformat(),
        "status": connection.status,
        "last_tested_at": connection.last_tested_at.isoformat() if connection.last_tested_at else None,
        "last_sync_at": connection.last_sync_at.isoformat() if connection.last_sync_at else None,
        "last_sync_status": connection.last_sync_status,
        "last_sync_records": connection.last_sync_records,
        "last_error": connection.last_error,
        "credential_configured": bool(connection.encrypted_api_key),
        "sync_watermarks": connection.sync_watermarks or {},
    }


async def _get_connection(db: AsyncSession, tenant_id: str) -> TenantSponteConnection | None:
    result = await db.execute(
        select(TenantSponteConnection).where(TenantSponteConnection.tenant_id == tenant_id)
    )
    return result.scalar_one_or_none()


@router.get("")
async def get_sponte_connection(
    auth: AuthContext = Depends(require_min_role("coordinator")),
    db: AsyncSession = Depends(get_db),
):
    connection = await _get_connection(db, auth.tenant_id)
    if not connection:
        return {"provider": "sponte", "configured": False, "credential_configured": False}
    return _connection_response(connection)


@router.put("")
async def configure_sponte_connection(
    body: SponteConfigurePayload,
    auth: AuthContext = Depends(require_min_role("coordinator")),
    db: AsyncSession = Depends(get_db),
):
    if body.initial_extraction_date > date.today():
        raise HTTPException(status_code=422, detail="A data inicial não pode estar no futuro.")
    active_job = await get_current_sponte_job(tenant_id=auth.tenant_id)
    if active_job and active_job.get("status") in {"queued", "running", "retrying"}:
        raise HTTPException(status_code=409, detail="Aguarde a sincronização Sponte terminar antes de alterar a conexão.")
    connection = await _get_connection(db, auth.tenant_id)
    if connection:
        client_changed = connection.client_code != body.client_code
        initial_date_changed = connection.initial_extraction_date != body.initial_extraction_date
        if client_changed and not body.api_key:
            raise HTTPException(status_code=422, detail="Informe a API Key ao alterar o código do cliente Sponte.")
        if client_changed:
            connection.sync_watermarks = {}
            connection.sync_catalogs = {}
        elif initial_date_changed:
            connection.sync_watermarks = {}
        connection.client_code = body.client_code
        connection.initial_extraction_date = body.initial_extraction_date
        if body.api_key:
            connection.encrypted_api_key = encrypt_api_token(body.api_key)
        connection.is_enabled = True
        connection.status = "configured"
        connection.last_error = None
    else:
        if not body.api_key:
            raise HTTPException(status_code=422, detail="Informe a API Key Sponte na primeira configuração.")
        connection = TenantSponteConnection(
            tenant_id=auth.tenant_id,
            client_code=body.client_code,
            initial_extraction_date=body.initial_extraction_date,
            encrypted_api_key=encrypt_api_token(body.api_key),
        )
        db.add(connection)
    await db.commit()
    await _set_tenant_rls_context(db, auth.tenant_id)
    await db.refresh(connection)
    return _connection_response(connection)


@router.post("/test")
async def test_sponte_connection(
    auth: AuthContext = Depends(require_min_role("coordinator")),
    db: AsyncSession = Depends(get_db),
):
    connection = await _get_connection(db, auth.tenant_id)
    if not connection or not connection.is_enabled:
        raise HTTPException(status_code=404, detail="Configure a conexão Sponte antes de testar.")
    client = await SponteApiClient.for_tenant(
        db, tenant_id=auth.tenant_id,
        api_key=decrypt_api_token(connection.encrypted_api_key),
        client_code=connection.client_code,
    )
    try:
        result = await client.test_connection()
        connection.status = "connected"
        connection.last_tested_at = datetime.now(timezone.utc)
        connection.last_error = None
        await db.commit()
        return result
    except (SponteConnectionError, ValueError) as exc:
        connection.status = "error"
        connection.last_tested_at = datetime.now(timezone.utc)
        connection.last_error = str(exc)
        await db.commit()
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        await client.close()


@router.post("/sync", status_code=202)
async def start_sponte_sync(
    auth: AuthContext = Depends(require_min_role("coordinator")),
    db: AsyncSession = Depends(get_db),
):
    connection = await _get_connection(db, auth.tenant_id)
    if not connection or not connection.is_enabled:
        raise HTTPException(status_code=404, detail="Configure a conexão Sponte antes de sincronizar.")
    try:
        job = await enqueue_sponte_sync(tenant_id=auth.tenant_id, tenant_slug=auth.tenant_slug)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "job_id": job["id"], "status": job.get("status"),
        "deduplicated": bool(job.get("deduplicated")), "progress": job.get("progress"),
    }


@router.get("/sync/current")
async def current_sponte_sync(
    auth: AuthContext = Depends(require_min_role("coordinator")),
):
    job = await get_current_sponte_job(tenant_id=auth.tenant_id)
    if not job:
        return None
    return {
        "job_id": job["id"], "status": job.get("status"),
        "progress": job.get("progress"), "result": job.get("result"),
        "last_error": job.get("last_error"), "attempt": job.get("attempt", 0),
    }


@router.get("/sync/{job_id}")
async def sponte_sync_status(
    job_id: str,
    auth: AuthContext = Depends(require_min_role("coordinator")),
):
    job = await get_sponte_job(job_id, tenant_id=auth.tenant_id)
    if not job:
        raise HTTPException(status_code=404, detail="Sincronização Sponte não encontrada.")
    return {
        "job_id": job["id"], "status": job.get("status"),
        "progress": job.get("progress"), "result": job.get("result"),
        "last_error": job.get("last_error"), "attempt": job.get("attempt", 0),
    }


@router.post("/sync/{job_id}/retry", status_code=202)
async def retry_sponte_sync_route(
    job_id: str,
    auth: AuthContext = Depends(require_min_role("coordinator")),
):
    try:
        job = await retry_sponte_sync(job_id, tenant_id=auth.tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not job:
        raise HTTPException(status_code=404, detail="Sincronização Sponte não encontrada.")
    return {"job_id": job["id"], "status": job.get("status"), "progress": job.get("progress")}
