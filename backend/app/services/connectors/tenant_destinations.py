"""Database-backed exact-host allowlists for tenant connector egress."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.auth import _set_tenant_rls_context
from app.models.connector_destination import TenantConnectorDestination
_DESTINATION_AUTHORIZATION_TOKEN = object()


def _destination_authorization_token() -> object:
    """Internal capability passed only by tenant-authorized client factories."""
    return _DESTINATION_AUTHORIZATION_TOKEN


def require_destination_authorization(token: object | None) -> None:
    """Prevent raw client construction outside tests and authorized factories."""
    if token is _DESTINATION_AUTHORIZATION_TOKEN:
        return
    if get_settings().app_env == "testing":
        return
    raise DestinationPolicyError(
        "Use a factory for_tenant após aprovar o destino no registro do tenant."
    )


from app.services.connectors.destination_policy import (
    DestinationPolicyError,
    validate_tenant_destination,
)


async def load_tenant_allowed_hosts(
    db: AsyncSession, *, tenant_id: str, connector_key: str
) -> set[str]:
    # Apply the tenant context on the same transaction before touching RLS tables.
    # Callers must still derive tenant_id from authenticated/job context, never request payload.
    await _set_tenant_rls_context(db, tenant_id)
    result = await db.execute(
        select(TenantConnectorDestination.hostname).where(
            TenantConnectorDestination.tenant_id == tenant_id,
            TenantConnectorDestination.connector_key == connector_key,
            TenantConnectorDestination.is_enabled.is_(True),
            TenantConnectorDestination.scheme == "https",
            TenantConnectorDestination.port == 443,
        )
    )
    hosts = set(result.scalars().all())
    if not hosts:
        raise DestinationPolicyError("Tenant não possui destino aprovado para este conector.")
    return hosts


async def authorize_tenant_destination(
    db: AsyncSession, *, tenant_id: str, connector_key: str, url: str
) -> str:
    hosts = await load_tenant_allowed_hosts(
        db, tenant_id=tenant_id, connector_key=connector_key
    )
    return validate_tenant_destination(
        tenant_id=tenant_id,
        url=url,
        tenant_allowed_hosts={tenant_id: hosts},
    )
