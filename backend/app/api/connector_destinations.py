"""Admin-only management of tenant outbound destination approvals."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthContext, require_min_role
from app.db.session import get_db
from app.models.connector_destination import (
    TenantConnectorDestination,
    TenantConnectorDestinationAudit,
)
from app.services.connectors.destination_policy import DestinationPolicyError, normalize_hostname

router = APIRouter(prefix="/security/connector-destinations", tags=["Segurança de egress"])


class DestinationApprovalPayload(BaseModel):
    connector_key: str = Field(min_length=2, max_length=40, pattern=r"^[a-z][a-z0-9_-]*$")
    hostname: str = Field(min_length=3, max_length=253)
    reason: str = Field(min_length=8, max_length=500)


def _actor(auth: AuthContext) -> str | None:
    return auth.user_id


@router.get("")
async def list_destinations(
    auth: AuthContext = Depends(require_min_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    rows = await db.execute(
        select(TenantConnectorDestination)
        .where(TenantConnectorDestination.tenant_id == auth.tenant_id)
        .order_by(TenantConnectorDestination.connector_key, TenantConnectorDestination.hostname)
    )
    return [{
        "id": row.id, "connector_key": row.connector_key, "hostname": row.hostname,
        "port": row.port, "enabled": row.is_enabled, "reason": row.approval_reason,
        "approved_at": row.approved_at.isoformat(),
    } for row in rows.scalars().all()]


@router.post("", status_code=status.HTTP_201_CREATED)
async def approve_destination(
    body: DestinationApprovalPayload,
    auth: AuthContext = Depends(require_min_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    try:
        hostname = normalize_hostname(body.hostname)
    except DestinationPolicyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    existing_result = await db.execute(
        select(TenantConnectorDestination).where(
            TenantConnectorDestination.tenant_id == auth.tenant_id,
            TenantConnectorDestination.connector_key == body.connector_key,
            TenantConnectorDestination.hostname == hostname,
            TenantConnectorDestination.port == 443,
        )
    )
    row = existing_result.scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if row:
        row.is_enabled = True
        row.approval_reason = body.reason
        row.approved_by_user_id = _actor(auth)
        row.approved_at = now
        row.updated_at = now
    else:
        row = TenantConnectorDestination(
            tenant_id=auth.tenant_id, connector_key=body.connector_key,
            hostname=hostname, scheme="https", port=443, is_enabled=True,
            approval_reason=body.reason, approved_by_user_id=_actor(auth),
        )
        db.add(row)
        await db.flush()
    db.add(TenantConnectorDestinationAudit(
        tenant_id=auth.tenant_id, destination_id=row.id,
        connector_key=body.connector_key, hostname=hostname, action="approved",
        reason=body.reason, actor_user_id=_actor(auth),
    ))
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Destino já cadastrado; atualize a aprovação existente.") from exc
    return {"id": row.id, "connector_key": row.connector_key, "hostname": row.hostname, "enabled": row.is_enabled}


@router.delete("/{destination_id}", status_code=status.HTTP_200_OK)
async def revoke_destination(
    destination_id: str,
    reason: str = Query(min_length=8, max_length=500),
    auth: AuthContext = Depends(require_min_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    try:
        parsed_id = str(uuid.UUID(destination_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Destino não encontrado.") from exc
    result = await db.execute(select(TenantConnectorDestination).where(
        TenantConnectorDestination.id == parsed_id,
        TenantConnectorDestination.tenant_id == auth.tenant_id,
    ))
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Destino não encontrado.")
    if row.is_enabled:
        row.is_enabled = False
        row.updated_at = datetime.now(timezone.utc)
        db.add(TenantConnectorDestinationAudit(
            tenant_id=auth.tenant_id, destination_id=row.id,
            connector_key=row.connector_key, hostname=row.hostname,
            action="revoked", reason=reason, actor_user_id=_actor(auth),
        ))
        await db.commit()
    return {"id": row.id, "enabled": row.is_enabled}
