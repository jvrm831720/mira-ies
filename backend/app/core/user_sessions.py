"""Criação e metadados de sessões autenticadas da MIRA."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.mira_security import TOKEN_TTL_SECONDS, issue_access_token
from app.models.auth import User, UserSession
from app.models.organization import Membership
from app.models.tenant import Tenant
from app.services.membership import ensure_membership, get_membership_for_tenant


def _device_label(user_agent: str | None) -> str:
    raw = (user_agent or "").strip()
    if not raw:
        return "Dispositivo desconhecido"
    lowered = raw.lower()
    browser = "Navegador"
    for token, label in (("edg/", "Edge"), ("opr/", "Opera"), ("firefox/", "Firefox"), ("chrome/", "Chrome"), ("safari/", "Safari")):
        if token in lowered:
            browser = label
            break
    platform = "Dispositivo"
    for token, label in (("windows", "Windows"), ("mac os", "macOS"), ("iphone", "iPhone"), ("ipad", "iPad"), ("android", "Android"), ("linux", "Linux")):
        if token in lowered:
            platform = label
            break
    return f"{browser} · {platform}"


async def create_user_session(
    db: AsyncSession,
    user: User,
    tenant: Tenant,
    request: Request | None = None,
    *,
    aal: int = 1,
    authenticated_at: int | None = None,
    membership: Membership | None = None,
) -> tuple[str, int]:
    """Registra sessão sem alterar um vínculo existente e emite JWT com mid."""
    now = datetime.now(timezone.utc)
    user_agent = request.headers.get("user-agent", "")[:1000] if request else ""
    ip_address = request.client.host[:64] if request and request.client else None
    session_id = str(uuid4())

    await db.execute(
        text("SELECT set_config('app.user_id', :user_id, true)"),
        {"user_id": user.id},
    )
    await db.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": tenant.id},
    )

    if membership is None:
        membership = await get_membership_for_tenant(
            db, user_id=user.id, tenant_id=tenant.id, for_update=True
        )
        if membership and membership.status != "active":
            raise ValueError("Não é possível criar sessão para membership inativa.")
        if not membership:
            if user.tenant_id != tenant.id:
                raise ValueError("Membership necessária para o workspace solicitado.")
            membership = await ensure_membership(
                db,
                user=user,
                tenant_id=tenant.id,
                role=user.role or "coordinator",
                custom_role_id=user.custom_role_id,
                origin="session_legacy_backfill",
                status="active",
            )
    elif (
        membership.user_id != user.id
        or membership.tenant_id != tenant.id
        or membership.status != "active"
    ):
        raise ValueError("Membership não corresponde ao workspace ativo da sessão.")

    session = UserSession(
        id=session_id,
        tenant_id=tenant.id,
        user_id=user.id,
        aal=aal,
        device_label=_device_label(user_agent),
        user_agent=user_agent or None,
        ip_address=ip_address,
        created_at=now,
        expires_at=now + timedelta(seconds=TOKEN_TTL_SECONDS),
    )
    db.add(session)
    return issue_access_token(
        user_id=user.id,
        tenant_id=tenant.id,
        auth_version=user.auth_version,
        session_id=session_id,
        aal=aal,
        membership_id=membership.id,
        authenticated_at=authenticated_at,
    )
