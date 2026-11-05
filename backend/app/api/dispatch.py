"""Dispatch control plane. No direct mass-send endpoint is exposed."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthContext, get_current_tenant, require_permission
from app.db.session import get_db
from app.services import dispatch_core as core

router = APIRouter(prefix="/dispatch", tags=["Dispatch Platform"])


class CampaignCreate(BaseModel):
    name: str = Field(min_length=3, max_length=160)
    purpose: Literal["retention", "collections"]
    channel: Literal["email", "sms", "whatsapp"]
    template_ref: str = Field(min_length=2, max_length=160)
    template_body: str = Field(min_length=3, max_length=2000)
    per_minute_limit: int = Field(default=10, ge=1, le=120)
    daily_contact_limit: int = Field(default=1, ge=1, le=3)
    timezone: str = Field(default="America/Sao_Paulo", max_length=80)
    start_hour: int = Field(default=9, ge=8, le=18)
    end_hour: int = Field(default=18, ge=9, le=20)


class Target(BaseModel):
    subject_type: Literal["student", "external"]
    subject_ref: str = Field(min_length=1, max_length=160)
    obligation_ref: str | None = Field(default=None, max_length=160)
    consent_ref: str = Field(min_length=8, max_length=200)


class TargetBatch(BaseModel):
    targets: list[Target] = Field(min_length=1, max_length=1000)


class Approval(BaseModel):
    authorization_ref: str = Field(min_length=8, max_length=200)


class Schedule(BaseModel):
    scheduled_for: datetime


def _actor(auth: AuthContext) -> str:
    if not auth.user_id:
        raise HTTPException(status_code=403, detail="Operação exige usuário humano autenticado.")
    return auth.user_id


def _error(exc: ValueError | LookupError) -> HTTPException:
    return HTTPException(status_code=404 if isinstance(exc, LookupError) else 422, detail=str(exc))


@router.get("/campaigns")
async def campaigns(
    limit: int = Query(50, ge=1, le=100),
    auth: AuthContext = Depends(require_permission("campaigns.view")),
    db: AsyncSession = Depends(get_db),
):
    return {"items": await core.list_campaigns(db, tenant_id=auth.tenant_id, limit=limit)}


@router.post("/campaigns", status_code=201)
async def create_campaign(
    body: CampaignCreate,
    auth: AuthContext = Depends(require_permission("campaigns.create")),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await core.create_campaign(
            db, tenant_id=auth.tenant_id, created_by=_actor(auth),
            name=body.name, purpose=body.purpose, channel=body.channel,
            template_ref=body.template_ref, template_body=body.template_body,
            per_minute_limit=body.per_minute_limit,
            daily_contact_limit=body.daily_contact_limit,
            timezone_name=body.timezone, start_hour=body.start_hour,
            end_hour=body.end_hour,
        )
    except ValueError as exc:
        await db.rollback()
        raise _error(exc) from exc


@router.get("/campaigns/{campaign_id}")
async def campaign_detail(
    campaign_id: str,
    auth: AuthContext = Depends(require_permission("campaigns.view")),
    db: AsyncSession = Depends(get_db),
):
    camp = await core.get_campaign(db, tenant_id=auth.tenant_id, campaign_id=campaign_id)
    if camp is None:
        raise HTTPException(status_code=404, detail="Campanha não encontrada.")
    return {
        "campaign": camp,
        "items": await core.campaign_items(
            db, tenant_id=auth.tenant_id, campaign_id=campaign_id,
        ),
    }


@router.post("/campaigns/{campaign_id}/targets")
async def stage_targets(
    campaign_id: str,
    body: TargetBatch,
    auth: AuthContext = Depends(require_permission("campaigns.edit")),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await core.enqueue_recipients(
            db, tenant_id=auth.tenant_id, campaign_id=campaign_id,
            targets=[target.model_dump() for target in body.targets],
            actor=_actor(auth),
        )
    except (ValueError, LookupError) as exc:
        await db.rollback()
        raise _error(exc) from exc



class FromProposal(BaseModel):
    proposal_id: str = Field(min_length=1, max_length=80)


@router.post("/campaigns/{campaign_id}/targets/from-proposal")
async def import_approved_proposal_audience(
    campaign_id: str, body: FromProposal,
    auth: AuthContext = Depends(require_permission("campaigns.edit")),
    db: AsyncSession = Depends(get_db),
):
    """Use approved, immutable audience snapshots—not a fresh unreviewed query."""
    from sqlalchemy import select
    from app.models.retention_campaign import RetentionCampaignProposal
    from app.services.campaign_proposals import hash_audience_snapshot

    actor = _actor(auth)
    campaign = await core.get_campaign(db, tenant_id=auth.tenant_id, campaign_id=campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campanha não encontrada.")
    if campaign["purpose"] != "retention":
        raise HTTPException(status_code=422, detail="Propostas de permanência não autorizam cobrança.")
    proposal = (await db.execute(select(RetentionCampaignProposal).where(
        RetentionCampaignProposal.tenant_id == auth.tenant_id,
        RetentionCampaignProposal.id == body.proposal_id,
    ))).scalar_one_or_none()
    if proposal is None or proposal.status != "approved":
        raise HTTPException(status_code=409, detail="Proposta inexistente ou ainda não aprovada.")
    if proposal.authorization_status != "institution_attested" or not proposal.authorization_reference:
        raise HTTPException(status_code=409, detail="Evidência institucional de autorização ausente.")
    audience = proposal.audience_snapshot or []
    if hash_audience_snapshot(audience) != proposal.audience_hash:
        raise HTTPException(status_code=409, detail="Snapshot da audiência foi alterado.")
    targets = [{
        "subject_type": "student",
        "subject_ref": record["student_id"],
        "consent_ref": proposal.authorization_reference,
    } for record in audience
        if campaign["channel"] in record.get("eligible_channels", [])
        and not record.get("blocked_reasons")
        and not record.get("internal_action_only")
    ]
    if not targets:
        raise HTTPException(status_code=409, detail="Nenhum destinatário elegível para este canal.")
    if len(targets) > 1000:
        raise HTTPException(status_code=422, detail="Snapshot muito grande: pagine sua importação por lote.")
    try:
        return await core.enqueue_recipients(
            db, tenant_id=auth.tenant_id, campaign_id=campaign_id,
            targets=targets, actor=actor,
        )
    except (ValueError, LookupError) as exc:
        await db.rollback()
        raise _error(exc) from exc


@router.post("/campaigns/{campaign_id}/approve")
async def approve(
    campaign_id: str,
    body: Approval,
    auth: AuthContext = Depends(require_permission("campaigns.approve")),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await core.transition_campaign(
            db, tenant_id=auth.tenant_id, campaign_id=campaign_id,
            actor=_actor(auth), target="approved",
            authorization_ref=body.authorization_ref,
        )
    except (ValueError, LookupError) as exc:
        await db.rollback()
        raise _error(exc) from exc


@router.post("/campaigns/{campaign_id}/schedule")
async def schedule(
    campaign_id: str, body: Schedule,
    auth: AuthContext = Depends(require_permission("campaigns.execute")),
    db: AsyncSession = Depends(get_db),
):
    if body.scheduled_for.tzinfo is None or body.scheduled_for.utcoffset() is None:
        raise HTTPException(status_code=422, detail="Agendamento precisa de fuso horário.")
    try:
        return await core.transition_campaign(
            db, tenant_id=auth.tenant_id, campaign_id=campaign_id,
            actor=_actor(auth), target="scheduled", scheduled_for=body.scheduled_for,
        )
    except (ValueError, LookupError) as exc:
        await db.rollback()
        raise _error(exc) from exc


@router.post("/campaigns/{campaign_id}/{action}")
async def change_campaign_state(
    campaign_id: str,
    action: Literal["start", "resume", "pause", "cancel"],
    auth: AuthContext = Depends(require_permission("campaigns.execute")),
    db: AsyncSession = Depends(get_db),
):
    target = {"start": "running", "resume": "running",
              "pause": "paused", "cancel": "cancelled"}[action]
    try:
        return await core.transition_campaign(
            db, tenant_id=auth.tenant_id, campaign_id=campaign_id,
            actor=_actor(auth), target=target,
        )
    except (ValueError, LookupError) as exc:
        await db.rollback()
        raise _error(exc) from exc



@router.get("/campaigns/{campaign_id}/replies")
async def campaign_replies(
    campaign_id: str,
    auth: AuthContext = Depends(require_permission("campaigns.view")),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import text
    campaign = await core.get_campaign(db, tenant_id=auth.tenant_id, campaign_id=campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campanha não encontrada.")
    rows = await db.execute(text("""
        SELECT inbound.event_kind, inbound.reply_intent,
               inbound.recommended_action, inbound.occurred_at
        FROM dispatch_inbound inbound
        JOIN dispatch_items item ON inbound.item_id=item.id
          AND inbound.tenant_id=item.tenant_id
        WHERE inbound.tenant_id=:tenant AND item.campaign_id=:campaign
        ORDER BY inbound.occurred_at DESC LIMIT 100
    """), {"tenant": auth.tenant_id, "campaign": campaign_id})
    return {"items": [dict(row) for row in rows.mappings().all()]}


@router.get("/metrics")
async def metrics(
    auth: AuthContext = Depends(require_permission("campaigns.view")),
    db: AsyncSession = Depends(get_db),
):
    items = await core.list_campaigns(db, tenant_id=auth.tenant_id, limit=100)
    return {
        "campaigns": len(items),
        "queued": sum(int(x["pending"]) for x in items),
        "accepted": sum(int(x["accepted"]) for x in items),
        "simulated": sum(int(x["simulated"]) for x in items),
        "problems": sum(int(x["problems"]) for x in items),
        "replies": sum(int(x["replied"]) for x in items),
        "note": "Aceito/entregue não é valor recuperado; concilie resultados financeiros.",
    }
