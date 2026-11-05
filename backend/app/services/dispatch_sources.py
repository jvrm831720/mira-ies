"""Shared MIRA source registry for dispatch context, never a second connector stack.

Composio accounts expose *authorized metadata* only. Selecting a connected
account does not execute a tool, import records, authorize contacting a person,
or establish that a payment was made. Provider credentials remain elsewhere.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.composio_connection import (
    TenantComposioAccount, TenantComposioToolkitPolicy,
)
from app.models.jacad_connection import TenantJacadConnection
from app.models.omie_connection import TenantOmieConnection
from app.models.retention_campaign import RetentionCampaignProposal
from app.models.sophia_connection import TenantSophiaConnection
from app.models.sponte_connection import TenantSponteConnection
from app.models.student import UploadBatch
from app.services.composio.gateway import composio_is_configured, composio_toolkit_allowed
from app.services.dispatch_core import bind_tenant

# These entries reference *existing* tenant-scoped connector records.
# Registry-only integrations without credentials or successful verification are
# deliberately not reported as dispatch-ready.
NATIVE_CONNECTORS = {
    "jacad": ("JACAD", TenantJacadConnection),
    "sophia": ("SophiA", TenantSophiaConnection),
    "sponte": ("Sponte", TenantSponteConnection),
    "omie": ("Omie", TenantOmieConnection),
}


_READ_VERBS = re.compile(r"(?:^|_)(?:GET|LIST|SEARCH|FETCH|READ|RETRIEVE|QUERY|LOOKUP|FIND|DESCRIBE|VIEW)(?:_|$)")
_MUTATING_VERBS = re.compile(r"(?:^|_)(?:SEND|POST|CREATE|UPDATE|EDIT|DELETE|REMOVE|WRITE|PATCH|PUT|PUBLISH|ARCHIVE|TRIGGER|EXECUTE|REPLY|TRANSFER|CHARGE|PAY)(?:_|$)")


def source_tool_is_read_only(slug: str) -> bool:
    """Conservative slug policy for context-only bindings, not a tool executor.

    Tool schema/side-effects must be verified separately before any real call.
    """
    name = slug.strip().upper()
    return bool(name and _READ_VERBS.search(name) and not _MUTATING_VERBS.search(name))


@dataclass(frozen=True)
class SourceState:
    available: bool
    reason: str


async def _native_record(db: AsyncSession, tenant_id: str, key: str):
    definition = NATIVE_CONNECTORS.get(key)
    if definition is None:
        return None
    model = definition[1]
    return (await db.execute(select(model).where(model.tenant_id == tenant_id))).scalar_one_or_none()


def _native_verified(record) -> bool:
    if record is None:
        return False
    return bool(
        record.is_enabled and record.last_tested_at is not None
        and record.status not in {"revoked", "disabled", "error"}
    )


async def require_source(
    db: AsyncSession, *, tenant_id: str, kind: str, reference: str | None = None,
    tool_slug: str | None = None, snapshot_hash: str | None = None,
) -> SourceState:
    """Recheck tenant ownership/policy when creating AND when executing.

    No remote calls, no Composio tool invocation. Manual imports are already
    normalized to MIRA students/contacts and carry their own contact basis.
    """
    await bind_tenant(db, tenant_id)
    if kind == "manual":
        if tool_slug:
            return SourceState(False, "manual_tool_not_allowed")
        if not reference:
            return SourceState(True, "manual_workspace_records")
        try:
            batch_id = str(UUID(reference))
        except (ValueError, TypeError):
            return SourceState(False, "invalid_upload_batch_id")
        batch = (await db.execute(select(UploadBatch).where(
            UploadBatch.id == batch_id, UploadBatch.tenant_id == tenant_id,
        ))).scalar_one_or_none()
        return SourceState(batch is not None, "upload_batch_found" if batch else "upload_batch_not_found")

    if kind == "native":
        if not reference or reference not in NATIVE_CONNECTORS or tool_slug:
            return SourceState(False, "native_connector_not_supported")
        record = await _native_record(db, tenant_id, reference)
        return SourceState(_native_verified(record), "native_verified" if _native_verified(record) else "native_not_verified")

    if kind == "composio":
        settings = get_settings()
        if not reference or not tool_slug or not composio_is_configured(settings):
            return SourceState(False, "composio_not_configured")
        account = (await db.execute(select(TenantComposioAccount).where(
            TenantComposioAccount.tenant_id == tenant_id,
            TenantComposioAccount.connected_account_id == reference,
        ))).scalar_one_or_none()
        if account is None or account.status != "active" or account.disconnected_at is not None:
            return SourceState(False, "composio_account_not_active")
        if not composio_toolkit_allowed(account.toolkit_slug, settings):
            return SourceState(False, "composio_toolkit_not_globally_allowed")
        policy = (await db.execute(select(TenantComposioToolkitPolicy).where(
            TenantComposioToolkitPolicy.tenant_id == tenant_id,
            TenantComposioToolkitPolicy.toolkit_slug == account.toolkit_slug,
        ))).scalar_one_or_none()
        if (
            policy is None or not policy.is_enabled
            or tool_slug not in (policy.tool_slugs or [])
            or not source_tool_is_read_only(tool_slug)
        ):
            return SourceState(False, "composio_read_tool_not_allowed_for_workspace")
        return SourceState(True, "composio_connection_policy_verified_metadata_only")

    if kind == "retention_proposal":
        # The snapshot is hashed once at materialization and DB-immutable thereafter.
        # Per-item checks stay O(1) for large approved audiences.
        if not reference or tool_slug or snapshot_hash is None:
            return SourceState(False, "retention_origin_missing")
        proposal = (await db.execute(select(RetentionCampaignProposal).where(
            RetentionCampaignProposal.tenant_id == tenant_id,
            RetentionCampaignProposal.id == reference,
        ))).scalar_one_or_none()
        if (
            proposal is None or proposal.status != "approved"
            or proposal.authorization_status != "institution_attested"
            or proposal.approved_by is None or proposal.approved_at is None
            or proposal.audience_hash != snapshot_hash
        ):
            return SourceState(False, "retention_approval_revoked_or_snapshot_changed")
        return SourceState(True, "existing_retention_governance_verified")

    return SourceState(False, "unsupported_source_kind")


async def list_sources(db: AsyncSession, *, tenant_id: str) -> dict:
    """Connection metadata by workspace. A connected app is NOT a live sender."""
    await bind_tenant(db, tenant_id)
    records: list[dict] = [
        {
            "kind": "manual", "reference": None, "name": "Dados já importados na MIRA",
            "category": "workspace", "connected": True, "can_bind": True,
            "tools": [], "automatic_ingestion": False,
            "note": "Alunos, contatos e bases já normalizados no workspace.",
        }
    ]
    for key, (label, _) in NATIVE_CONNECTORS.items():
        record = await _native_record(db, tenant_id, key)
        if record is None:
            continue
        verified = _native_verified(record)
        records.append({
            "kind": "native", "reference": key, "name": label,
            "category": "native", "connected": bool(record.is_enabled),
            "can_bind": verified, "tools": [], "automatic_ingestion": False,
            "note": (
                "Conexão validada para vincular origem; dados precisam estar normalizados na MIRA."
                if verified else "Configuração presente, mas sem homologação de conexão para disparos."
            ),
        })
    settings = get_settings()
    policy_rows = (await db.execute(select(TenantComposioToolkitPolicy).where(
        TenantComposioToolkitPolicy.tenant_id == tenant_id,
    ))).scalars().all()
    policies = {row.toolkit_slug: row for row in policy_rows}
    accounts = (await db.execute(select(TenantComposioAccount).where(
        TenantComposioAccount.tenant_id == tenant_id,
    ))).scalars().all()
    for account in accounts:
        policy = policies.get(account.toolkit_slug)
        connected = account.status == "active" and account.disconnected_at is None
        selected_tools = (
            [slug for slug in (policy.tool_slugs or []) if isinstance(slug, str) and source_tool_is_read_only(slug)]
            if policy and policy.is_enabled else []
        )
        can_bind = bool(
            connected and composio_is_configured(settings)
            and composio_toolkit_allowed(account.toolkit_slug, settings)
            and policy and policy.is_enabled and selected_tools
        )
        records.append({
            "kind": "composio",
            "reference": account.connected_account_id,
            "name": account.display_name or account.toolkit_slug,
            "toolkit": account.toolkit_slug,
            "category": "composio",
            "connected": connected,
            "can_bind": can_bind,
            "tools": selected_tools if can_bind else [],
            "automatic_ingestion": False,
            "note": (
                "Conta e política verificadas. Usar ferramentas requer o executor Composio autorizado."
                if can_bind else "Conexão ou política ainda não habilitada para uso."
            ),
        })
    return {
        "items": records,
        "composio_tool_execution_enabled": bool(
            settings.composio_tool_execution_enabled and composio_is_configured(settings)
        ),
        "composio_ingestion_enabled": bool(
            settings.dispatch_composio_ingestion_enabled
            and settings.dispatch_composio_ingestion_read_tools.strip()
            and settings.dispatch_composio_data_key
            and composio_is_configured(settings)
        ),
    }
