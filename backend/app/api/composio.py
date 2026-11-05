"""Tenant-scoped Composio catalog, policy and connection endpoints."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.auth import AuthContext, require_permission
from app.db.session import get_db
from app.models.composio_connection import TenantComposioToolAudit, TenantComposioToolkitPolicy
from app.models.composio_approval import TenantComposioToolApproval
from app.services.composio.policy import ComposioPolicyDenied, authorize_tool_request, decrypt_arguments, redact_arguments
from app.services.composio.categories import (
    annotate_toolkit,
    communication_category,
    crm_category,
    documents_category,
    productivity_category,
    data_analysis_category,
    support_category,
)
from app.services.composio.client import (
    ComposioSDKUnavailable,
    list_toolkits,
    list_tools_for_toolkit,
    validate_tool_slugs,
)
from app.services.composio.connections import (
    ConnectionDenied,
    complete_connect_callback,
    list_tenant_accounts,
    revoke_tenant_account,
    start_connect_link,
)
from app.services.composio.gateway import ComposioNotConfigured, require_composio_configuration
from app.services.composio.sessions import ensure_tenant_session

router = APIRouter(prefix="/integrations/composio", tags=["Composio"])


class ToolkitPolicyPayload(BaseModel):
    enabled: bool
    tool_slugs: list[str] = Field(default_factory=list, max_length=500)


class StartConnectPayload(BaseModel):
    toolkit_slug: str = Field(min_length=1, max_length=80)
    auth_config_id: str = Field(min_length=1, max_length=80)


class CompleteConnectPayload(BaseModel):
    state: str = Field(min_length=8, max_length=128)
    connected_account_id: str = Field(min_length=1, max_length=120)


def _catalog_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ComposioNotConfigured):
        return HTTPException(status_code=503, detail="Integração Composio desativada ou sem configuração.")
    if isinstance(exc, ComposioSDKUnavailable):
        return HTTPException(status_code=503, detail="SDK Composio indisponível no backend.")
    if isinstance(exc, ConnectionDenied):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=502, detail="Falha na operação Composio.")


@router.get("/catalog")
async def get_catalog(
    auth: AuthContext = Depends(require_permission("settings.manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        require_composio_configuration()
        catalog = await run_in_threadpool(list_toolkits)
    except Exception as exc:
        raise _catalog_error(exc) from exc

    rows = await db.execute(
        select(TenantComposioToolkitPolicy).where(
            TenantComposioToolkitPolicy.tenant_id == auth.tenant_id
        )
    )
    policies = {row.toolkit_slug: row for row in rows.scalars().all()}
    return {
        "source": "composio_live_catalog",
        "items": [{
            **annotate_toolkit(item),
            "enabled": bool(policies.get(item["slug"]) and policies[item["slug"]].is_enabled),
            "selected_tool_slugs": (
                policies[item["slug"]].tool_slugs
                if item["slug"] in policies else []
            ),
        } for item in catalog],
        "total": len(catalog),
    }


@router.get("/catalog/categories")
async def get_catalog_categories(
    auth: AuthContext = Depends(require_permission("settings.manage")),
):
    """Return MIRA's curated integration categories and native channel providers."""
    return {
        "items": [
            communication_category(),
            crm_category(),
            documents_category(),
            productivity_category(),
            data_analysis_category(),
            support_category(),
        ],
        "total": 6,
    }


@router.put("/catalog/{toolkit_slug}/policy")
async def update_toolkit_policy(
    toolkit_slug: str,
    body: ToolkitPolicyPayload,
    auth: AuthContext = Depends(require_permission("settings.manage")),
    db: AsyncSession = Depends(get_db),
):
    slug = toolkit_slug.strip().lower()
    if not slug or len(slug) > 80 or not slug.replace("_", "").replace("-", "").isalnum():
        raise HTTPException(status_code=422, detail="Toolkit slug inválido.")

    try:
        require_composio_configuration()
        known_toolkits = {item["slug"] for item in await run_in_threadpool(list_toolkits)}
        if slug not in known_toolkits:
            raise HTTPException(status_code=404, detail="Toolkit não encontrado no catálogo Composio.")
        tools = await run_in_threadpool(validate_tool_slugs, slug, body.tool_slugs) if body.tool_slugs else []
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise _catalog_error(exc) from exc

    if body.enabled and not tools:
        raise HTTPException(
            status_code=422,
            detail="Selecione ao menos uma ferramenta antes de habilitar o toolkit.",
        )

    result = await db.execute(select(TenantComposioToolkitPolicy).where(
        TenantComposioToolkitPolicy.tenant_id == auth.tenant_id,
        TenantComposioToolkitPolicy.toolkit_slug == slug,
    ).with_for_update())
    row = result.scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if row is None:
        row = TenantComposioToolkitPolicy(
            tenant_id=auth.tenant_id,
            toolkit_slug=slug,
            is_enabled=body.enabled,
            tool_slugs=tools,
            updated_by_user_id=auth.user_id,
            updated_at=now,
        )
        db.add(row)
    else:
        row.is_enabled = body.enabled
        row.tool_slugs = tools
        row.updated_by_user_id = auth.user_id
        row.updated_at = now

    # A policy change revokes any pending request whose tool is no longer exposed.
    pending_result = await db.execute(select(TenantComposioToolApproval).where(
        TenantComposioToolApproval.tenant_id == auth.tenant_id,
        TenantComposioToolApproval.toolkit_slug == slug,
        TenantComposioToolApproval.status == "pending_approval",
    ).with_for_update())
    selected_tools = {item.upper() for item in tools}
    for approval in pending_result.scalars().all():
        if not body.enabled or approval.tool_slug.upper() not in selected_tools:
            approval.status = "cancelled"
            db.add(_approval_audit(
                tenant_id=auth.tenant_id, actor_user_id=auth.user_id,
                row=approval, approval_status="cancelled",
            ))
    await db.commit()
    return {
        "toolkit_slug": row.toolkit_slug,
        "enabled": row.is_enabled,
        "tool_slugs": row.tool_slugs,
        "updated_at": row.updated_at.isoformat(),
    }


@router.get("/catalog/{toolkit_slug}/tools")
async def get_toolkit_tools(
    toolkit_slug: str,
    auth: AuthContext = Depends(require_permission("settings.manage")),
):
    slug = toolkit_slug.strip().lower()
    if not slug or len(slug) > 80 or not slug.replace("_", "").replace("-", "").isalnum():
        raise HTTPException(status_code=422, detail="Toolkit slug inválido.")
    try:
        require_composio_configuration()
        known_toolkits = {item["slug"] for item in await run_in_threadpool(list_toolkits)}
        if slug not in known_toolkits:
            raise HTTPException(status_code=404, detail="Toolkit não encontrado no catálogo Composio.")
        tools = await run_in_threadpool(list_tools_for_toolkit, slug)
    except HTTPException:
        raise
    except Exception as exc:
        raise _catalog_error(exc) from exc
    return {"toolkit_slug": slug, "items": tools, "total": len(tools)}


@router.post("/session")
async def provision_session(
    auth: AuthContext = Depends(require_permission("settings.manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        require_composio_configuration()
        row = await ensure_tenant_session(
            db, tenant_id=auth.tenant_id, actor_user_id=auth.user_id
        )
        await db.commit()
    except Exception as exc:
        raise _catalog_error(exc) from exc
    return {
        "tenant_id": row.tenant_id,
        "composio_user_id": row.composio_user_id,
        "status": row.status,
        "session_id": row.session_id,
    }


@router.post("/connections/start")
async def start_connection(
    body: StartConnectPayload,
    auth: AuthContext = Depends(require_permission("settings.manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await start_connect_link(
            db,
            tenant_id=auth.tenant_id,
            actor_user_id=auth.user_id,
            toolkit_slug=body.toolkit_slug,
            auth_config_id=body.auth_config_id,
        )
    except Exception as exc:
        raise _catalog_error(exc) from exc
    return result


@router.post("/connections/complete")
async def complete_connection(
    body: CompleteConnectPayload,
    auth: AuthContext = Depends(require_permission("settings.manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await complete_connect_callback(
            db,
            tenant_id=auth.tenant_id,
            state_token=body.state,
            connected_account_id=body.connected_account_id,
        )
    except Exception as exc:
        raise _catalog_error(exc) from exc
    return result


@router.get("/connections")
async def list_connections(
    sync: bool = Query(default=False),
    auth: AuthContext = Depends(require_permission("settings.manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        items = await list_tenant_accounts(
            db, tenant_id=auth.tenant_id, sync_remote=sync
        )
    except Exception as exc:
        raise _catalog_error(exc) from exc
    return {"items": items, "total": len(items)}


@router.delete("/connections/{connected_account_id}")
async def delete_connection(
    connected_account_id: str,
    auth: AuthContext = Depends(require_permission("settings.manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await revoke_tenant_account(
            db,
            tenant_id=auth.tenant_id,
            connected_account_id=connected_account_id,
            revoke_remote=True,
            actor_user_id=auth.user_id,
        )
    except Exception as exc:
        raise _catalog_error(exc) from exc
    return result



class ToolApprovalRequestPayload(BaseModel):
    connected_account_id: str = Field(min_length=1, max_length=120)
    toolkit_slug: str = Field(min_length=1, max_length=80)
    tool_slug: str = Field(min_length=1, max_length=120)
    arguments: dict = Field(default_factory=dict)
    idempotency_key: str = Field(min_length=16, max_length=120, pattern="^[A-Za-z0-9._:-]+$")


class ToolApprovalReviewPayload(BaseModel):
    decision: str = Field(pattern="^(approve|reject)$")


def _require_human_aal2(auth: AuthContext) -> None:
    if not auth.user_id or not auth.session_id or auth.aal < 2:
        raise HTTPException(status_code=403, detail="Esta operação exige uma sessão humana autenticada com AAL2.")


def _approval_audit(*, tenant_id: str, actor_user_id: str | None, row: TenantComposioToolApproval, audit_status: str = "pending_approval", approval_status: str | None = None) -> TenantComposioToolAudit:
    return TenantComposioToolAudit(
        tenant_id=tenant_id, actor_user_id=actor_user_id,
        connected_account_id=row.connected_account_id,
        toolkit_slug=row.toolkit_slug, tool_slug=row.tool_slug,
        status=audit_status, approval_required=True,
        approval_status=approval_status or row.status,
        request_fingerprint=row.request_fingerprint,
    )


def _approval_response(row: TenantComposioToolApproval) -> dict:
    try:
        preview = redact_arguments(decrypt_arguments(tenant_id=row.tenant_id, ciphertext=row.arguments_ciphertext))
    except ComposioPolicyDenied:
        preview = {"error": "Não foi possível validar a prévia protegida."}
    return {
        "id": row.id, "connected_account_id": row.connected_account_id,
        "toolkit_slug": row.toolkit_slug, "tool_slug": row.tool_slug,
        "status": row.status, "arguments_preview": preview,
        "request_fingerprint": row.request_fingerprint,
        "requested_by_user_id": row.requested_by_user_id,
        "reviewed_by_user_id": row.reviewed_by_user_id,
        "requested_at": row.requested_at.isoformat(),
        "expires_at": row.expires_at.isoformat(),
        "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
    }


@router.post("/approvals", status_code=201)
async def request_tool_approval(
    body: ToolApprovalRequestPayload,
    auth: AuthContext = Depends(require_permission("settings.manage")),
    db: AsyncSession = Depends(get_db),
):
    _require_human_aal2(auth)
    try:
        authorized = await authorize_tool_request(
            db, auth=auth, connected_account_id=body.connected_account_id,
            toolkit_slug=body.toolkit_slug, tool_slug=body.tool_slug,
            arguments=body.arguments,
        )
    except ComposioPolicyDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as exc:
        raise _catalog_error(exc) from exc

    lock_key = f"composio-approval:{auth.tenant_id}:{body.idempotency_key}"
    await db.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(lock_key, 0))))
    existing_result = await db.execute(select(TenantComposioToolApproval).where(
        TenantComposioToolApproval.tenant_id == auth.tenant_id,
        TenantComposioToolApproval.idempotency_key == body.idempotency_key,
    ))
    existing = existing_result.scalar_one_or_none()
    if existing:
        if existing.request_fingerprint != authorized["request_fingerprint"]:
            raise HTTPException(status_code=409, detail="Idempotency-Key já foi usada para uma solicitação diferente.")
        return _approval_response(existing)

    now = datetime.now(timezone.utc)
    row = TenantComposioToolApproval(
        tenant_id=auth.tenant_id, connected_account_id=authorized["connected_account_id"],
        requested_by_user_id=auth.user_id, toolkit_slug=authorized["toolkit_slug"],
        tool_slug=authorized["tool_slug"], arguments_ciphertext=authorized["arguments_ciphertext"],
        request_fingerprint=authorized["request_fingerprint"], idempotency_key=body.idempotency_key,
        status="pending_approval", requested_at=now, expires_at=now + timedelta(minutes=30),
    )
    db.add(row)
    await db.flush()
    db.add(_approval_audit(tenant_id=auth.tenant_id, actor_user_id=auth.user_id, row=row))
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Solicitação concorrente; repita com a mesma chave de idempotência.") from exc
    return _approval_response(row)


@router.get("/approvals")
async def list_tool_approvals(
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=100),
    auth: AuthContext = Depends(require_permission("settings.manage")),
    db: AsyncSession = Depends(get_db),
):
    _require_human_aal2(auth)
    allowed = {"pending_approval", "approved", "rejected", "expired", "cancelled", "executing", "succeeded", "failed", "unknown"}
    if status_filter and status_filter not in allowed:
        raise HTTPException(status_code=422, detail="Filtro de status inválido.")
    query = select(TenantComposioToolApproval).where(TenantComposioToolApproval.tenant_id == auth.tenant_id)
    if status_filter:
        query = query.where(TenantComposioToolApproval.status == status_filter)
    result = await db.execute(query.order_by(TenantComposioToolApproval.requested_at.desc()).limit(limit).with_for_update())
    rows = result.scalars().all()
    now = datetime.now(timezone.utc)
    expired_any = False
    for row in rows:
        if row.status == "pending_approval" and row.expires_at <= now:
            row.status = "expired"
            expired_any = True
            db.add(_approval_audit(tenant_id=auth.tenant_id, actor_user_id=None, row=row, approval_status="expired"))
    if expired_any:
        await db.commit()
    return {"items": [_approval_response(row) for row in rows], "total": len(rows)}


@router.post("/approvals/{approval_id}/review")
async def review_tool_approval(
    approval_id: str,
    body: ToolApprovalReviewPayload,
    auth: AuthContext = Depends(require_permission("settings.manage")),
    db: AsyncSession = Depends(get_db),
):
    _require_human_aal2(auth)
    result = await db.execute(select(TenantComposioToolApproval).where(
        TenantComposioToolApproval.id == approval_id,
        TenantComposioToolApproval.tenant_id == auth.tenant_id,
    ).with_for_update())
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada.")
    if row.requested_by_user_id == auth.user_id:
        raise HTTPException(status_code=403, detail="A regra four-eyes impede aprovar a própria solicitação.")
    if row.status != "pending_approval":
        raise HTTPException(status_code=409, detail="Solicitação não está aguardando revisão.")
    now = datetime.now(timezone.utc)
    if row.expires_at <= now:
        row.status = "expired"
        db.add(_approval_audit(tenant_id=auth.tenant_id, actor_user_id=auth.user_id, row=row, approval_status="expired"))
        await db.commit()
        raise HTTPException(status_code=410, detail="Solicitação expirada.")
    row.status = "approved" if body.decision == "approve" else "rejected"
    row.reviewed_by_user_id = auth.user_id
    row.reviewed_at = now
    db.add(_approval_audit(tenant_id=auth.tenant_id, actor_user_id=auth.user_id, row=row, approval_status=row.status))
    await db.commit()
    return _approval_response(row)


@router.post("/approvals/{approval_id}/cancel")
async def cancel_tool_approval(
    approval_id: str,
    auth: AuthContext = Depends(require_permission("settings.manage")),
    db: AsyncSession = Depends(get_db),
):
    _require_human_aal2(auth)
    result = await db.execute(select(TenantComposioToolApproval).where(
        TenantComposioToolApproval.id == approval_id,
        TenantComposioToolApproval.tenant_id == auth.tenant_id,
    ).with_for_update())
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada.")
    if row.requested_by_user_id != auth.user_id:
        raise HTTPException(status_code=403, detail="Somente o solicitante pode cancelar esta solicitação.")
    if row.status != "pending_approval":
        raise HTTPException(status_code=409, detail="Somente solicitações pendentes podem ser canceladas.")
    if row.expires_at <= datetime.now(timezone.utc):
        row.status = "expired"
        db.add(_approval_audit(tenant_id=auth.tenant_id, actor_user_id=auth.user_id, row=row, approval_status="expired"))
        await db.commit()
        raise HTTPException(status_code=410, detail="Solicitação expirada.")
    row.status = "cancelled"
    db.add(_approval_audit(tenant_id=auth.tenant_id, actor_user_id=auth.user_id, row=row, approval_status="cancelled"))
    await db.commit()
    return _approval_response(row)
