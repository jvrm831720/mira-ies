"""Read-only administration endpoints for the internal MIRA Control Center."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.control_center_auth import admin_permission
from app.core.config import get_settings
from app.db.session import get_db
from app.models.auth import User
from app.models.control_center import AdminAuditEvent, AdminPrincipal
from app.models.tenant import Tenant

router = APIRouter(prefix="/admin/control-center", tags=["MIRA Control Center - Admin"])


def _channel_status(settings) -> list[dict]:
    whatsapp_providers = []
    if settings.waha_api_url and settings.waha_api_key:
        whatsapp_providers.append("WAHA")
    if settings.evolution_api_url and settings.evolution_api_key and settings.evolution_instance:
        whatsapp_providers.append("Evolution API")
    return [
        {
            "id": "whatsapp",
            "name": "WhatsApp",
            "configured": bool(whatsapp_providers),
            "providers": whatsapp_providers,
            "note": "Credenciais presentes; conectividade ainda precisa ser verificada.",
        },
        {
            "id": "email",
            "name": "E-mail",
            "configured": bool(settings.resend_api_key and settings.email_from),
            "providers": ["Resend"] if settings.resend_api_key and settings.email_from else [],
            "note": "Configuração de envio de e-mail.",
        },
        {
            "id": "sms",
            "name": "SMS",
            "configured": bool(settings.twilio_account_sid and settings.twilio_auth_token and settings.twilio_from),
            "providers": ["Twilio"] if settings.twilio_account_sid and settings.twilio_auth_token and settings.twilio_from else [],
            "note": "Configuração do provedor; nenhum SMS é enviado por esta tela.",
        },
    ]


@router.get("/overview")
async def overview(
    _admin: AdminPrincipal = Depends(admin_permission("orgs:read")),
    db: AsyncSession = Depends(get_db),
):
    tenants_total = await db.scalar(select(func.count()).select_from(Tenant)) or 0
    tenants_active = await db.scalar(select(func.count()).select_from(Tenant).where(Tenant.is_active.is_(True))) or 0
    members_total = await db.scalar(select(func.count()).select_from(User)) or 0
    members_active = await db.scalar(select(func.count()).select_from(User).where(User.is_active.is_(True))) or 0
    admins_total = await db.scalar(select(func.count()).select_from(AdminPrincipal)) or 0
    recent_result = await db.execute(
        select(AdminAuditEvent, AdminPrincipal.email)
        .outerjoin(AdminPrincipal, AdminPrincipal.id == AdminAuditEvent.actor_admin_id)
        .order_by(AdminAuditEvent.created_at.desc())
        .limit(8)
    )
    recent_events = [
        {
            "id": event.id,
            "actor_email": actor_email,
            "action": event.action,
            "result": event.result,
            "reason": event.reason,
            "created_at": event.created_at.isoformat() if event.created_at else None,
        }
        for event, actor_email in recent_result.all()
    ]
    return {
        "metrics": {
            "organizations_total": tenants_total,
            "organizations_active": tenants_active,
            "members_total": members_total,
            "members_active": members_active,
            "admins_total": admins_total,
        },
        "channels": _channel_status(get_settings()),
        "recent_events": recent_events,
    }


@router.get("/organizations")
async def list_organizations(
    _admin: AdminPrincipal = Depends(admin_permission("orgs:read")),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=100, ge=1, le=200),
):
    member_counts = (
        select(User.tenant_id, func.count(User.id).label("members_count"))
        .group_by(User.tenant_id)
        .subquery()
    )
    result = await db.execute(
        select(Tenant, func.coalesce(member_counts.c.members_count, 0))
        .outerjoin(member_counts, member_counts.c.tenant_id == Tenant.id)
        .order_by(Tenant.created_at.desc())
        .limit(limit)
    )
    return {
        "organizations": [
            {
                "id": tenant.id,
                "name": tenant.name,
                "slug": tenant.slug,
                "segment": tenant.segment,
                "is_active": tenant.is_active,
                "members_count": members_count,
                "created_at": tenant.created_at.isoformat() if tenant.created_at else None,
                "model_ready": tenant.tenant_model_ready,
            }
            for tenant, members_count in result.all()
        ]
    }


@router.get("/members")
async def list_members(
    _admin: AdminPrincipal = Depends(admin_permission("members:read")),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=100, ge=1, le=200),
):
    result = await db.execute(
        select(User, Tenant.name)
        .join(Tenant, Tenant.id == User.tenant_id)
        .order_by(User.created_at.desc())
        .limit(limit)
    )
    return {
        "members": [
            {
                "id": member.id,
                "name": member.display_name,
                "email": member.email,
                "role": member.role,
                "is_active": member.is_active,
                "organization": organization_name,
                "created_at": member.created_at.isoformat() if member.created_at else None,
            }
            for member, organization_name in result.all()
        ]
    }


@router.get("/audit")
async def list_audit_events(
    _admin: AdminPrincipal = Depends(admin_permission("audit:read")),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=100, ge=1, le=200),
):
    result = await db.execute(
        select(AdminAuditEvent, AdminPrincipal.email)
        .outerjoin(AdminPrincipal, AdminPrincipal.id == AdminAuditEvent.actor_admin_id)
        .order_by(AdminAuditEvent.created_at.desc())
        .limit(limit)
    )
    return {
        "events": [
            {
                "id": event.id,
                "actor_email": actor_email,
                "action": event.action,
                "result": event.result,
                "reason": event.reason,
                "target_type": event.target_type,
                "target_id": event.target_id,
                "request_id": event.request_id,
                "created_at": event.created_at.isoformat() if event.created_at else None,
            }
            for event, actor_email in result.all()
        ]
    }
