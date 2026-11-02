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
from app.models.student import Student
from app.services.connectors import get_connector, ingest_records
from app.services.connectors.jacad_mapping import enrich_jacad_students
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
    if connection.default_org_id is None:
        raise HTTPException(
            status_code=422,
            detail="Informe o ID da organização JACAD para sincronizar matrículas e dados financeiros.",
        )

    client = JacadApiClient(connection.base_url, decrypt_api_token(connection.encrypted_api_token))
    try:
        source_students = await client.fetch_students(org_id=connection.default_org_id)
        enrollments = await client.fetch_enrollments(org_id=connection.default_org_id)
        financial_summaries = await client.fetch_financial_summaries(org_id=connection.default_org_id)
        enriched_source, jacad_metadata = enrich_jacad_students(
            source_students, enrollments, financial_summaries
        )
        connector = get_connector("jacad")
        records = connector.transform({"elements": enriched_source})
        if not records:
            raise JacadConnectionError("A consulta terminou sem alunos válidos para ingestão.")

        result = await ingest_records(
            db,
            records=records,
            source="jacad",
            filename="jacad_academic_financial_sync.json",
            auto_score=False,
            tenant_id=auth.tenant_id,
            tenant_slug=auth.tenant_slug,
        )

        # Keep only the minimum provider identifiers and documented finance
        # summary needed for traceability. Never persist the full provider payload.
        await _set_tenant_rls_context(db, auth.tenant_id)
        matriculas = [record["matricula"] for record in records]
        query = select(Student).where(
            Student.tenant_id == auth.tenant_id,
            Student.matricula.in_(matriculas),
        )
        students_result = await db.execute(query)
        imported_students = list(students_result.scalars().all())
        imported_at = datetime.now(timezone.utc).isoformat()
        provenance_fields = (
            "status_aluno", "curso", "turma", "status_financeiro",
            "dias_atraso_boleto", "recorrencia_atrasos", "saldo_devedor",
        )
        for student in imported_students:
            raw_data = dict(student.raw_data or {})
            raw_data["jacad"] = jacad_metadata.get(student.matricula, {})
            provenance = raw_data.get("_mira_provenance")
            provenance = dict(provenance) if isinstance(provenance, dict) else {}
            for field in provenance_fields:
                if getattr(student, field, None) is not None or field in {
                    "status_financeiro", "dias_atraso_boleto", "recorrencia_atrasos"
                }:
                    provenance[field] = {
                        "source_type": "jacad_api",
                        "source_filename": "jacad_academic_financial_sync",
                        "source_batch_id": str(result["batch"].id),
                        "imported_at": imported_at,
                        # JACAD's record-level dataAlteracao is not a field-level
                        # observation timestamp. Do not present import time as observed_at.
                        "observed_at": None,
                        "observed_at_source_column": None,
                        "freshness_basis": "source_observation_timestamp_unavailable",
                    }
            raw_data["_mira_provenance"] = provenance
            student.raw_data = raw_data

        await _set_tenant_rls_context(db, auth.tenant_id)
        connection.status = "connected"
        connection.last_sync_at = datetime.now(timezone.utc)
        connection.last_sync_status = "success"
        connection.last_sync_records = int(result.get("students_imported", 0))
        connection.last_error = None
        await db.commit()

        financial_status_coverage = sum(
            1 for item in enriched_source
            if str(item.get("status_financeiro") or "").upper()
            in {"VENCIDO", "EM_ABERTO", "PAGO", "SEM_FINANCEIRO"}
        )
        return {
            "status": "success",
            "source_records": len(source_students),
            "students_imported": result.get("students_imported", 0),
            "enrollments_received": len(enrollments),
            "financial_summaries_received": len(financial_summaries),
            "students_with_financial_status": financial_status_coverage,
            "scoring": "disabled_until_predictive_coverage_is_complete",
            "batch": result.get("batch"),
            "quality": result.get("quality"),
        }
    except (JacadConnectionError, ValueError) as exc:
        await _set_tenant_rls_context(db, auth.tenant_id)
        connection.status = "error"
        connection.last_sync_at = datetime.now(timezone.utc)
        connection.last_sync_status = "failed"
        connection.last_error = str(exc)
        await db.commit()
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        await client.close()
