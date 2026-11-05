"""Provision and load tenant-owned Composio session metadata (no credentials)."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.composio_connection import TenantComposioSession
from app.services.composio.identity import composio_user_id_for_tenant


async def ensure_tenant_session(
    db: AsyncSession,
    *,
    tenant_id: str,
    actor_user_id: str | None,
) -> TenantComposioSession:
    """Return the tenant's Composio identity row, creating it when missing."""
    result = await db.execute(
        select(TenantComposioSession).where(TenantComposioSession.tenant_id == tenant_id)
    )
    row = result.scalar_one_or_none()
    if row is not None:
        return row

    row = TenantComposioSession(
        tenant_id=tenant_id,
        composio_user_id=composio_user_id_for_tenant(tenant_id),
        status="provisioned",
        created_by_user_id=actor_user_id,
        updated_at=datetime.now(timezone.utc),
    )
    db.add(row)
    await db.flush()
    return row
