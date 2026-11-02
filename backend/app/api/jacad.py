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
from app.services.connectors import get_connector, ingest_records
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
    api_token: str = Field(min_length=1, max_length=40)
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
    encrypted = encrypt_api_token(body.api_token)
    if connection:
        connection.base_url = body.base_url
        connection.encrypted_api_token = encrypted
        connection.default_org_id = body.default_org_id
        connection.is_enabled = True
        connection.status = "configured"
        connection.last_error = None
    else:
        connection = TenantJacadConnection(
            tenant_id=auth.tenant_id,
            base_url=body.base_url,
            encrypted_api_token=encrypted,
            default_org_id=body.default_org_id,
        )
        db.add(connection)
    await db.commit()
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
    client = JacadApiClient(connection.base_url, decrypt_api_token(connection.encrypted_api_token))
    try:
        result = await client.test_connection()
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


@router.post("/sync")
async def sync_jacad_students(
    auth: AuthContext = Depends(require_min_role("coordinator")),
    db: AsyncSession = Depends(get_db),
):
    connection = await _get_connection(db, auth.tenant_id)
    if not connection or not connection.is_enabled:
        raise HTTPException(status_code=404, detail="Configure a conexão JACAD antes de sincronizar.")
    client = JacadApiClient(connection.base_url, decrypt_api_token(connection.encrypted_api_token))
    try:
        source_students = await client.fetch_students()
        connector = get_connector("jacad")
        records = connector.transform({"elements": source_students})
        if not records:
            raise JacadConnectionError("A consulta terminou sem alunos válidos para ingestão.")
        # Cadastro de alunos não fornece os sete sinais preditivos com semântica
        # suficiente. Não calcular score a partir de campos ausentes.
        result = await ingest_records(
            db,
            records=records,
            source="jacad",
            filename="jacad_students_sync.json",
            auto_score=False,
            tenant_id=auth.tenant_id,
            tenant_slug=auth.tenant_slug,
        )
        await _set_tenant_rls_context(db, auth.tenant_id)
        connection.status = "connected"
        connection.last_sync_at = datetime.now(timezone.utc)
        connection.last_sync_status = "success"
        connection.last_sync_records = int(result.get("students_imported", 0))
        connection.last_error = None
        await db.commit()
        return {
            "status": "success",
            "source_records": len(source_students),
            "students_imported": result.get("students_imported", 0),
            "scoring": "disabled_missing_predictive_sources",
            "batch": result.get("batch"),
            "quality": result.get("quality"),
        }
    except (JacadConnectionError, ValueError) as exc:
        connection.status = "error"
        connection.last_sync_at = datetime.now(timezone.utc)
        connection.last_sync_status = "failed"
        connection.last_error = str(exc)
        await db.commit()
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        await client.close()
