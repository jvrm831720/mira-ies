"""Tenant-scoped Omie configuration and read-only finance queries."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthContext, require_permission
from app.db.session import get_db
from app.models.omie_connection import TenantOmieConnection
from app.services.connectors.omie_api import OmieApiClient, OmieApiError, OmieCredentials
from app.services.connectors.omie_secrets import decrypt_omie_secret, encrypt_omie_secret

router = APIRouter(prefix="/integrations/omie", tags=["Integração Omie"])


class OmieConfigurePayload(BaseModel):
    app_hash: str = Field(min_length=1, max_length=160)
    access_token: str = Field(min_length=16, max_length=4096)
    refresh_token: str = Field(min_length=16, max_length=4096)
    token_expires_at: datetime | None = None


def _connection_response(row: TenantOmieConnection | None) -> dict[str, Any]:
    if not row:
        return {"provider": "omie", "configured": False, "enabled": False}
    return {
        "provider": "omie",
        "configured": True,
        "enabled": row.is_enabled,
        "status": row.status,
        "token_expires_at": row.token_expires_at.isoformat(),
        "last_tested_at": row.last_tested_at.isoformat() if row.last_tested_at else None,
        "last_error_code": row.last_error_code,
    }


async def _get_connection(db: AsyncSession, tenant_id: str) -> TenantOmieConnection | None:
    result = await db.execute(
        select(TenantOmieConnection).where(TenantOmieConnection.tenant_id == tenant_id)
    )
    return result.scalar_one_or_none()


async def _client_for_tenant(
    db: AsyncSession, tenant_id: str
) -> tuple[TenantOmieConnection, OmieApiClient]:
    row = await _get_connection(db, tenant_id)
    if not row or not row.is_enabled:
        raise HTTPException(status_code=404, detail="Configure a conexão Omie antes de consultar.")
    credentials = OmieCredentials(
        app_hash=row.app_hash,
        access_token=decrypt_omie_secret(row.encrypted_access_token),
        refresh_token=decrypt_omie_secret(row.encrypted_refresh_token),
        expires_at=row.token_expires_at,
    )
    return row, OmieApiClient(credentials)


async def _persist_rotated_credentials(
    db: AsyncSession, row: TenantOmieConnection, client: OmieApiClient
) -> None:
    row.encrypted_access_token = encrypt_omie_secret(client.credentials.access_token)
    row.encrypted_refresh_token = encrypt_omie_secret(client.credentials.refresh_token)
    row.token_expires_at = client.credentials.expires_at
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()


async def _read_finance(
    *,
    resource: str,
    page: int,
    page_size: int,
    auth: AuthContext,
    db: AsyncSession,
) -> dict[str, Any]:
    row, client = await _client_for_tenant(db, auth.tenant_id)
    try:
        if resource == "accounts-receivable":
            payload = await client.list_accounts_receivable(page=page, page_size=page_size)
        elif resource == "accounts-payable":
            payload = await client.list_accounts_payable(page=page, page_size=page_size)
        else:
            raise HTTPException(status_code=404, detail="Consulta Omie não permitida.")
        await _persist_rotated_credentials(db, row, client)
        return payload
    except OmieApiError as exc:
        row.status = "error" if not exc.retryable else row.status
        row.last_error_code = exc.code[:40]
        await db.commit()
        raise HTTPException(
            status_code=503 if exc.retryable else 502,
            detail="Falha na consulta financeira ao Omie.",
        ) from exc
    finally:
        await client.close()


@router.get("")
async def get_omie_connection(
    auth: AuthContext = Depends(require_permission("settings.manage")),
    db: AsyncSession = Depends(get_db),
):
    return _connection_response(await _get_connection(db, auth.tenant_id))


@router.put("/connection")
async def configure_omie_connection(
    body: OmieConfigurePayload,
    auth: AuthContext = Depends(require_permission("settings.manage")),
    db: AsyncSession = Depends(get_db),
):
    expires_at = body.token_expires_at or (datetime.now(timezone.utc) + timedelta(hours=24))
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=422, detail="O token informado já está expirado.")

    row = await _get_connection(db, auth.tenant_id)
    encrypted_access = encrypt_omie_secret(body.access_token)
    encrypted_refresh = encrypt_omie_secret(body.refresh_token)
    if row:
        row.app_hash = body.app_hash
        row.encrypted_access_token = encrypted_access
        row.encrypted_refresh_token = encrypted_refresh
        row.token_expires_at = expires_at
        row.is_enabled = True
        row.status = "configured"
        row.last_error_code = None
    else:
        row = TenantOmieConnection(
            tenant_id=auth.tenant_id,
            app_hash=body.app_hash,
            encrypted_access_token=encrypted_access,
            encrypted_refresh_token=encrypted_refresh,
            token_expires_at=expires_at,
        )
        db.add(row)
    await db.commit()
    return _connection_response(row)


@router.post("/test")
async def test_omie_connection(
    auth: AuthContext = Depends(require_permission("settings.manage")),
    db: AsyncSession = Depends(get_db),
):
    row, client = await _client_for_tenant(db, auth.tenant_id)
    try:
        # Test only read permissions; no financial mutation is exposed.
        receivable = await client.list_accounts_receivable(page=1, page_size=1)
        payable = await client.list_accounts_payable(page=1, page_size=1)
        await _persist_rotated_credentials(db, row, client)
        row.status = "connected"
        row.last_tested_at = datetime.now(timezone.utc)
        row.last_error_code = None
        await db.commit()
        return {
            "status": "connected",
            "accounts_receivable_page": receivable.get("pagina", 1),
            "accounts_payable_page": payable.get("pagina", 1),
        }
    except OmieApiError as exc:
        row.status = "error"
        row.last_tested_at = datetime.now(timezone.utc)
        row.last_error_code = exc.code[:40]
        await db.commit()
        raise HTTPException(status_code=503 if exc.retryable else 502, detail="Falha ao validar a conexão Omie.") from exc
    finally:
        await client.close()


@router.get("/accounts-receivable")
async def list_omie_accounts_receivable(
    page: int = Query(default=1, ge=1, le=100000),
    page_size: int = Query(default=50, ge=1, le=100),
    auth: AuthContext = Depends(require_permission("settings.manage")),
    db: AsyncSession = Depends(get_db),
):
    return await _read_finance(
        resource="accounts-receivable", page=page, page_size=page_size, auth=auth, db=db
    )


@router.get("/accounts-payable")
async def list_omie_accounts_payable(
    page: int = Query(default=1, ge=1, le=100000),
    page_size: int = Query(default=50, ge=1, le=100),
    auth: AuthContext = Depends(require_permission("settings.manage")),
    db: AsyncSession = Depends(get_db),
):
    return await _read_finance(
        resource="accounts-payable", page=page, page_size=page_size, auth=auth, db=db
    )


@router.delete("/connection")
async def disable_omie_connection(
    auth: AuthContext = Depends(require_permission("settings.manage")),
    db: AsyncSession = Depends(get_db),
):
    row = await _get_connection(db, auth.tenant_id)
    if not row:
        raise HTTPException(status_code=404, detail="Conexão Omie não encontrada.")
    row.is_enabled = False
    row.status = "disabled"
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return {"provider": "omie", "enabled": False, "status": "disabled"}
