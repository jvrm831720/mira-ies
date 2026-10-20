"""APIs de ingestao multi-fonte — tenant_id obrigatorio em toda escrita."""

from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from app.db.session import get_db
from app.core.auth import AuthContext, get_current_tenant
from app.services.connectors import list_connectors, get_connector, ingest_records

router = APIRouter()


class GenericIngestRequest(BaseModel):
    students: list[dict[str, Any]] = Field(..., min_length=1)
    source: str = Field(default="generic")
    auto_score: bool = Field(default=True)


async def _read_json(request: Request) -> Any:
    try:
        return await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Body JSON invalido")


def _unwrap_payload(payload: Any) -> tuple[Any, bool]:
    auto_score = True
    if isinstance(payload, dict):
        if "auto_score" in payload:
            auto_score = bool(payload.get("auto_score", True))
        for key in ("data", "alunos", "students", "items", "records", "results"):
            if key in payload:
                return payload[key], auto_score
        return payload, auto_score
    return payload, auto_score


async def _ingest_via_connector(
    connector_id: str,
    payload: Any,
    auto_score: bool,
    db: AsyncSession,
    *,
    tenant_id: str,
    tenant_slug: str | None = None,
):
    try:
        conn = get_connector(connector_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    records = conn.transform(payload)  # type: ignore
    if not records:
        raise HTTPException(status_code=422, detail=f"Nenhum registro valido para '{connector_id}'")
    try:
        return await ingest_records(
            db,
            records=records,
            source=connector_id,
            filename=f"{connector_id}_api.json",
            auto_score=auto_score,
            tenant_id=tenant_id,
            tenant_slug=tenant_slug,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro na ingestao: {str(e)}")


@router.get("/connectors")
async def catalog_connectors():
    items = list_connectors()
    return {"count": len(items), "connectors": [c.model_dump() for c in items]}


@router.get("/connectors/{connector_id}")
async def get_connector_detail(connector_id: str):
    try:
        return get_connector(connector_id).info.model_dump()
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/ingest/students", status_code=201)
async def ingest_canonical(
    body: GenericIngestRequest,
    auth: AuthContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    conn = get_connector("generic")
    records = conn.transform({"students": body.students})  # type: ignore
    if not records:
        raise HTTPException(status_code=422, detail="Nenhum aluno valido no payload")
    try:
        return await ingest_records(
            db,
            records=records,
            source=body.source or "generic",
            filename="canonical_json.json",
            auto_score=body.auto_score,
            tenant_id=auth.tenant_id,
            tenant_slug=auth.tenant_slug,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/connectors/{connector_id}/students", status_code=201)
@router.post("/connectors/{connector_id}/sync", status_code=201)
async def ingest_by_connector(
    connector_id: str,
    request: Request,
    auto_score: bool = Query(True),
    auth: AuthContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    payload = await _read_json(request)
    data, envelope_score = _unwrap_payload(payload)
    if isinstance(payload, dict) and "auto_score" in payload:
        auto_score = envelope_score
    return await _ingest_via_connector(
        connector_id, data, auto_score, db,
        tenant_id=auth.tenant_id, tenant_slug=auth.tenant_slug,
    )


@router.post("/webhooks/moodle", status_code=201)
async def webhook_moodle(
    request: Request,
    auth: AuthContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
    auto_score: bool = Query(True),
):
    payload = await _read_json(request)
    if isinstance(payload, dict) and "eventname" in payload:
        payload = [payload]
    return await _ingest_via_connector(
        "moodle", payload, auto_score, db,
        tenant_id=auth.tenant_id, tenant_slug=auth.tenant_slug,
    )


@router.post("/webhooks/canvas", status_code=201)
async def webhook_canvas(
    request: Request,
    auth: AuthContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
    auto_score: bool = Query(True),
):
    return await _ingest_via_connector(
        "canvas", await _read_json(request), auto_score, db,
        tenant_id=auth.tenant_id, tenant_slug=auth.tenant_slug,
    )


@router.post("/webhooks/erp/{connector_id}", status_code=201)
async def webhook_erp(
    connector_id: str,
    request: Request,
    auth: AuthContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
    auto_score: bool = Query(True),
):
    allowed = {"jacad", "sponte", "sophia", "gvcollege", "wpensar", "isaac"}
    cid = connector_id.lower()
    if cid not in allowed:
        raise HTTPException(status_code=404, detail=f"Webhook ERP nao suportado: {connector_id}")
    payload = await _read_json(request)
    data, s = _unwrap_payload(payload)
    return await _ingest_via_connector(
        cid,
        data,
        s if isinstance(payload, dict) and "auto_score" in payload else auto_score,
        db,
        tenant_id=auth.tenant_id,
        tenant_slug=auth.tenant_slug,
    )
