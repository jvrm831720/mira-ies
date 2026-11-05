"""Tenant-approved Composio read tools import normalized context to MIRA Dispatch.

No arbitrary session or tool proxy is available to the frontend. Write tools,
cross-tenant accounts and missing AAL2 are denied before SDK execution.
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthContext, require_permission
from app.db.session import get_db
from app.services import dispatch_composio_imports as ingest

router = APIRouter(prefix="/dispatch/composio", tags=["Dispatch Composio Ingestion"])


class ReadImport(BaseModel):
    connected_account_id: str = Field(min_length=1, max_length=120)
    tool_slug: str = Field(min_length=1, max_length=120)
    arguments: dict = Field(default_factory=dict)
    rows_path: str = Field(default="", max_length=240)
    record_id_field: str = Field(min_length=1, max_length=240)
    subject_ref_field: str = Field(min_length=1, max_length=240)
    subject_type: Literal["student", "external"]
    record_type: Literal["contact", "obligation", "generic"]
    field_map: dict[str, str] = Field(default_factory=dict, max_length=12)


def require_aal2(auth: AuthContext) -> str:
    if not auth.user_id or not auth.session_id or auth.aal < 2:
        raise HTTPException(
            status_code=403, detail="Importação exige sessão humana MFA (AAL2).",
        )
    return auth.user_id


@router.post("/imports", status_code=201)
async def execute_read_import(
    body: ReadImport,
    idempotency_key: str = Header(
        ..., alias="Idempotency-Key", min_length=16, max_length=120,
    ),
    auth: AuthContext = Depends(require_permission("data.import")),
    db: AsyncSession = Depends(get_db),
):
    actor = require_aal2(auth)
    try:
        return await ingest.import_read_tool(
            db, tenant_id=auth.tenant_id, actor_id=actor,
            account_id=body.connected_account_id,
            tool_slug=body.tool_slug, arguments=body.arguments,
            rows_path=body.rows_path,
            record_id_field=body.record_id_field,
            subject_ref_field=body.subject_ref_field,
            subject_type=body.subject_type,
            record_type=body.record_type,
            field_map=body.field_map,
            idempotency_key=idempotency_key,
        )
    except ingest.ComposioIngestDenied as exc:
        await db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (ValueError, TypeError) as exc:
        await db.rollback()
        raise HTTPException(status_code=422, detail="Configuração de importação inválida.") from exc


@router.get("/imports")
async def import_history(
    limit: int = Query(30, ge=1, le=100),
    auth: AuthContext = Depends(require_permission("campaigns.view")),
    db: AsyncSession = Depends(get_db),
):
    return {"items": await ingest.list_import_runs(
        db, tenant_id=auth.tenant_id, limit=limit,
    )}


@router.get("/observations")
async def observation_counts(
    auth: AuthContext = Depends(require_permission("campaigns.view")),
    db: AsyncSession = Depends(get_db),
):
    # Metadata only. Never expose source payload or PII.
    return {"items": await ingest.list_observation_counts(
        db, tenant_id=auth.tenant_id,
    )}


class StageFromComposio(BaseModel):
    source_record_ids: list[str] = Field(default_factory=list, max_length=100)


@router.post("/campaigns/{campaign_id}/stage", status_code=201)
async def stage_campaign_from_read_observations(
    campaign_id: str, body: StageFromComposio,
    auth: AuthContext = Depends(require_permission("campaigns.edit")),
    db: AsyncSession = Depends(get_db),
):
    actor = require_aal2(auth)
    try:
        return await ingest.stage_authorized_observations(
            db, tenant_id=auth.tenant_id, actor_id=actor,
            campaign_id=campaign_id, source_record_ids=body.source_record_ids,
        )
    except LookupError as exc:
        await db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ingest.ComposioIngestDenied as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
