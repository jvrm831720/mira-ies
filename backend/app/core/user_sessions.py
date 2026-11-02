"""Criação e metadados de sessões autenticadas da MIRA."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.mira_security import TOKEN_TTL_SECONDS, issue_access_token
from app.models.auth import User, UserSession
from app.models.tenant import Tenant


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


def create_user_session(
    db: AsyncSession,
    user: User,
    tenant: Tenant,
    request: Request | None = None,
    *,
    aal: int = 1,
) -> tuple[str, int]:
    """Registra a sessão antes de emitir o JWT que a referencia."""
    now = datetime.now(timezone.utc)
    user_agent = request.headers.get("user-agent", "")[:1000] if request else ""
    ip_address = request.client.host[:64] if request and request.client else None
    session_id = str(uuid4())
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
    )
