"""Read-only administration endpoints for the internal MIRA Control Center."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import UUID as PyUUID
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.control_center_auth import admin_permission
from app.core.config import get_settings
from app.db.session import get_db
from app.models.auth import User
from app.models.control_center import AdminAuditEvent, AdminBillingRecord, AdminPrincipal
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

    return {
        "metrics": {
            "organizations_total": tenants_total,
            "organizations_active": tenants_active,
            "members_total": members_total,
            "members_active": members_active,
            "admins_total": admins_total,
        },
        "channels": _channel_status(get_settings()),
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



class BillingRecordCreate(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=64)
    @field_validator("tenant_id")
    @classmethod
    def normalize_tenant_id(cls, value: str) -> str:
        try:
            return str(PyUUID(value))
        except ValueError as exc:
            raise ValueError("Identificador de instituição inválido.") from exc

    plan_name: str = Field(min_length=2, max_length=120)
    plan_price_brl: float = Field(ge=0, le=100000000)
    billing_cycle: Literal["monthly", "yearly"] = "monthly"
    payment_link: str | None = Field(default=None, max_length=500)
    due_at: datetime
    plan_status: Literal["active", "paused", "cancelled"] = "active"
    payment_status: Literal["pending", "paid"] = "pending"
    notes: str | None = Field(default=None, max_length=500)

    @field_validator("payment_link")
    @classmethod
    def validate_payment_link(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        parsed = urlsplit(value.strip())
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
            raise ValueError("O link de pagamento deve ser uma URL HTTPS válida.")
        return value.strip()

    @field_validator("due_at")
    @classmethod
    def normalize_due_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value


class BillingRecordUpdate(BaseModel):
    plan_name: str | None = Field(default=None, min_length=2, max_length=120)
    plan_price_brl: float | None = Field(default=None, ge=0, le=100000000)
    billing_cycle: Literal["monthly", "yearly"] | None = None
    payment_link: str | None = Field(default=None, max_length=500)
    due_at: datetime | None = None
    plan_status: Literal["active", "paused", "cancelled"] | None = None
    payment_status: Literal["pending", "paid"] | None = None
    notes: str | None = Field(default=None, max_length=500)

    @field_validator("payment_link")
    @classmethod
    def validate_payment_link(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        parsed = urlsplit(value.strip())
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
            raise ValueError("O link de pagamento deve ser uma URL HTTPS válida.")
        return value.strip()

    @field_validator("due_at")
    @classmethod
    def normalize_due_at(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value


def _billing_dict(record: AdminBillingRecord, organization_name: str) -> dict:
    due_at = record.due_at
    now = datetime.now(timezone.utc)
    if due_at.tzinfo is None:
        due_at = due_at.replace(tzinfo=timezone.utc)
    overdue = record.payment_status != "paid" and due_at < now
    days_until_due = (due_at.date() - now.date()).days
    return {
        "id": record.id,
        "tenant_id": record.tenant_id,
        "organization_name": organization_name,
        "plan_name": record.plan_name,
        "plan_price_brl": float(record.plan_price_brl),
        "billing_cycle": record.billing_cycle,
        "payment_link": record.payment_link,
        "due_at": due_at.isoformat(),
        "plan_status": record.plan_status,
        "payment_status": record.payment_status,
        "is_overdue": overdue,
        "days_until_due": days_until_due,
        "notes": record.notes,
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
    }


@router.get("/billing-records")
async def list_billing_records(
    _admin: AdminPrincipal = Depends(admin_permission("billing:read")),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=200, ge=1, le=500),
):
    result = await db.execute(
        select(AdminBillingRecord, Tenant.name)
        .join(Tenant, Tenant.id == AdminBillingRecord.tenant_id)
        .order_by(AdminBillingRecord.due_at.asc())
        .limit(limit)
    )
    records = [_billing_dict(record, organization_name) for record, organization_name in result.all()]
    return {
        "records": records,
        "summary": {
            "total": len(records),
            "overdue": sum(1 for record in records if record["is_overdue"]),
            "due_soon": sum(1 for record in records if not record["is_overdue"] and record["payment_status"] != "paid" and 0 <= record["days_until_due"] <= 30),
            "pending": sum(1 for record in records if record["payment_status"] != "paid"),
        },
    }


@router.post("/billing-records", status_code=status.HTTP_201_CREATED)
async def create_billing_record(
    body: BillingRecordCreate,
    request: Request,
    admin: AdminPrincipal = Depends(admin_permission("billing:write")),
    db: AsyncSession = Depends(get_db),
):
    tenant = await db.get(Tenant, body.tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Instituição não encontrada.")
    existing = await db.scalar(
        select(AdminBillingRecord.id).where(AdminBillingRecord.tenant_id == body.tenant_id)
    )
    if existing:
        raise HTTPException(status_code=409, detail="Já existe um registro financeiro para esta instituição. Atualize o registro existente.")
    data = body.model_dump()
    record = AdminBillingRecord(**data, created_by_admin_id=admin.id)
    db.add(record)
    await db.flush()
    db.add(AdminAuditEvent(
        actor_admin_id=admin.id, action="billing_record_created", result="success",
        target_type="billing_record", target_id=record.id, reason="Registro financeiro criado",
        request_id=request.headers.get("x-request-id"),
        metadata_redacted={"tenant_id": tenant.id, "billing_cycle": body.billing_cycle},
    ))
    await db.commit()
    await db.refresh(record)
    return _billing_dict(record, tenant.name)


@router.patch("/billing-records/{record_id}")
async def update_billing_record(
    record_id: str,
    body: BillingRecordUpdate,
    request: Request,
    admin: AdminPrincipal = Depends(admin_permission("billing:write")),
    db: AsyncSession = Depends(get_db),
):
    record = await db.get(AdminBillingRecord, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Registro financeiro não encontrado.")
    data = body.model_dump(exclude_unset=True)
    for key, value in data.items():
        if value is not None or key in {"payment_link", "notes"}:
            setattr(record, key, value)
    db.add(AdminAuditEvent(
        actor_admin_id=admin.id, action="billing_record_updated", result="success",
        target_type="billing_record", target_id=record.id, reason="Registro financeiro atualizado",
        request_id=request.headers.get("x-request-id"),
        metadata_redacted={"fields_updated": sorted(data.keys())},
    ))
    await db.commit()
    await db.refresh(record)
    tenant = await db.get(Tenant, record.tenant_id)
    return _billing_dict(record, tenant.name if tenant else "Instituição removida")



class OrganizationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    segment: str | None = Field(default=None, max_length=80)
    is_active: bool | None = None


class MemberUpdate(BaseModel):
    is_active: bool | None = None
    role: Literal["admin", "coordinator", "operator", "viewer"] | None = None


@router.patch("/organizations/{tenant_id}")
async def update_organization(
    tenant_id: str,
    body: OrganizationUpdate,
    request: Request,
    admin: AdminPrincipal = Depends(admin_permission("orgs:write")),
    db: AsyncSession = Depends(get_db),
):
    try:
        normalized_id = str(PyUUID(tenant_id))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Identificador de instituição inválido.") from exc
    tenant = await db.get(Tenant, normalized_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Instituição não encontrada.")
    changes = body.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=422, detail="Informe ao menos um campo para atualizar.")
    before = {key: getattr(tenant, key) for key in changes}
    for key, value in changes.items():
        if value is not None or key in {"segment", "name"}:
            setattr(tenant, key, value)
    after = {key: getattr(tenant, key) for key in changes}
    db.add(AdminAuditEvent(
        actor_admin_id=admin.id, action="organization_updated", result="success",
        target_type="organization", target_id=tenant.id,
        reason="Dados da instituição atualizados",
        request_id=request.headers.get("x-request-id"),
        metadata_redacted={"fields_updated": sorted(changes.keys()), "before": before, "after": after},
    ))
    await db.commit()
    return {"id": tenant.id, "name": tenant.name, "slug": tenant.slug, "segment": tenant.segment, "is_active": tenant.is_active}


@router.patch("/members/{member_id}")
async def update_member(
    member_id: str,
    body: MemberUpdate,
    request: Request,
    admin: AdminPrincipal = Depends(admin_permission("members:write")),
    db: AsyncSession = Depends(get_db),
):
    try:
        normalized_id = str(PyUUID(member_id))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Identificador de membro inválido.") from exc
    member = await db.get(User, normalized_id)
    if not member:
        raise HTTPException(status_code=404, detail="Membro não encontrado.")
    changes = body.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=422, detail="Informe ao menos um campo para atualizar.")
    before = {key: getattr(member, key) for key in changes}
    for key, value in changes.items():
        if value is not None:
            setattr(member, key, value)
    after = {key: getattr(member, key) for key in changes}
    member.auth_version += 1
    db.add(AdminAuditEvent(
        actor_admin_id=admin.id, action="member_updated", result="success",
        target_type="member", target_id=member.id,
        reason="Permissões ou status do membro atualizados",
        request_id=request.headers.get("x-request-id"),
        metadata_redacted={"fields_updated": sorted(changes.keys()), "before": before, "after": after},
    ))
    await db.commit()
    return {"id": member.id, "name": member.display_name, "email": member.email, "role": member.role, "is_active": member.is_active}
