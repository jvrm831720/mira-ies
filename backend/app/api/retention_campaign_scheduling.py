"""Scheduling metadata for approved retention campaign proposals.

Wave 1.4B persists an explicit schedule only. It does not enqueue, dispatch,
or execute campaigns.
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthContext, _set_tenant_rls_context, require_min_role
from app.db.session import get_db
from app.models.retention_campaign import (
    RetentionCampaignProposal,
    RetentionCampaignProposalAuditEvent,
)
from app.services.campaign_lifecycle import validate_campaign_transition

router = APIRouter(
    prefix="/agents/retention/campaigns/intelligence",
    tags=["Agendamento de Campanhas"],
)


class ScheduleInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # An explicit UTC offset is required. The IANA zone is validated separately.
    scheduled_for: datetime
    schedule_timezone: str = Field(min_length=1, max_length=64)


def _human_admin(auth: AuthContext) -> str:
    if not auth.user_id or auth.aal < 2:
        raise HTTPException(
            status_code=403,
            detail="O agendamento exige uma sessão humana com MFA (AAL2).",
        )
    return auth.user_id


def _validate_schedule(body: ScheduleInput) -> tuple[datetime, str]:
    value = body.scheduled_for
    if value.tzinfo is None or value.utcoffset() is None:
        raise HTTPException(
            status_code=422,
            detail="Informe scheduled_for com offset UTC explícito.",
        )
    timezone_name = body.schedule_timezone.strip()
    if not timezone_name:
        raise HTTPException(status_code=422, detail="Informe um fuso IANA válido.")
    try:
        zone = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError):
        raise HTTPException(status_code=422, detail="Fuso IANA desconhecido.") from None

    normalized = value.astimezone(timezone.utc)
    expected_offset = normalized.astimezone(zone).utcoffset()
    if value.utcoffset() != expected_offset:
        raise HTTPException(
            status_code=422,
            detail="O offset informado não corresponde ao fuso IANA na data selecionada.",
        )
    if normalized <= datetime.now(timezone.utc):
        raise HTTPException(status_code=422, detail="O agendamento deve ocorrer no futuro.")
    return normalized, timezone_name


async def _locked_proposal(
    db: AsyncSession, auth: AuthContext, proposal_id: str
) -> RetentionCampaignProposal:
    proposal = (await db.execute(
        select(RetentionCampaignProposal)
        .where(
            RetentionCampaignProposal.id == proposal_id,
            RetentionCampaignProposal.tenant_id == auth.tenant_id,
        )
        .with_for_update()
    )).scalar_one_or_none()
    if proposal is None:
        raise HTTPException(status_code=404, detail="Proposta não encontrada.")
    return proposal


def _audit(
    db: AsyncSession,
    proposal: RetentionCampaignProposal,
    actor_id: str,
    event_type: str,
    details: dict,
) -> None:
    db.add(RetentionCampaignProposalAuditEvent(
        tenant_id=proposal.tenant_id,
        proposal_id=proposal.id,
        actor_user_id=actor_id,
        event_type=event_type,
        revision=proposal.revision,
        details=details,
    ))


def _serialize_schedule(proposal: RetentionCampaignProposal) -> dict:
    return {
        "proposal_id": proposal.id,
        "tenant_id": proposal.tenant_id,
        "title": proposal.title,
        "status": proposal.status,
        "scheduled_for": proposal.scheduled_for,
        "schedule_timezone": proposal.schedule_timezone,
        "revision": proposal.revision,
        "execution_enabled": False,
        "dispatch_created": False,
    }


@router.post("/proposals/{proposal_id}/schedule")
async def schedule_campaign_proposal(
    proposal_id: str,
    body: ScheduleInput,
    auth: AuthContext = Depends(require_min_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    actor_id = _human_admin(auth)
    scheduled_for, timezone_name = _validate_schedule(body)
    proposal = await _locked_proposal(db, auth, proposal_id)
    if proposal.status != "approved":
        raise HTTPException(
            status_code=409,
            detail="Somente propostas aprovadas podem ser agendadas.",
        )
    try:
        validate_campaign_transition(proposal.status, "scheduled")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None

    proposal.status = "scheduled"
    proposal.scheduled_for = scheduled_for
    proposal.schedule_timezone = timezone_name
    proposal.revision += 1
    proposal.updated_at = datetime.now(timezone.utc)
    _audit(db, proposal, actor_id, "proposal.scheduled", {
        "scheduled_for": scheduled_for.isoformat(),
        "schedule_timezone": timezone_name,
        "execution_enabled": False,
    })
    await db.commit()
    # set_config(..., true) is transaction-local; commit clears the tenant RLS context.
    await _set_tenant_rls_context(db, auth.tenant_id)
    await db.refresh(proposal)
    return _serialize_schedule(proposal)


@router.delete("/proposals/{proposal_id}/schedule")
async def remove_campaign_schedule(
    proposal_id: str,
    auth: AuthContext = Depends(require_min_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    actor_id = _human_admin(auth)
    proposal = await _locked_proposal(db, auth, proposal_id)
    if proposal.status != "scheduled":
        raise HTTPException(status_code=409, detail="A proposta não possui agendamento ativo.")
    try:
        validate_campaign_transition(proposal.status, "approved")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None

    previous_schedule = {
        "scheduled_for": proposal.scheduled_for.isoformat() if proposal.scheduled_for else None,
        "schedule_timezone": proposal.schedule_timezone,
    }
    proposal.status = "approved"
    proposal.scheduled_for = None
    proposal.schedule_timezone = None
    proposal.revision += 1
    proposal.updated_at = datetime.now(timezone.utc)
    _audit(db, proposal, actor_id, "proposal.schedule_removed", {
        **previous_schedule,
        "execution_enabled": False,
    })
    await db.commit()
    # set_config(..., true) is transaction-local; commit clears the tenant RLS context.
    await _set_tenant_rls_context(db, auth.tenant_id)
    await db.refresh(proposal)
    return _serialize_schedule(proposal)


@router.get("/schedule")
async def list_campaign_schedule(
    auth: AuthContext = Depends(require_min_role("coordinator")),
    db: AsyncSession = Depends(get_db),
):
    rows = list((await db.execute(
        select(RetentionCampaignProposal)
        .where(
            RetentionCampaignProposal.tenant_id == auth.tenant_id,
            RetentionCampaignProposal.status == "scheduled",
        )
        .order_by(RetentionCampaignProposal.scheduled_for.asc())
        .limit(200)
    )).scalars().all())
    return {
        "tenant_id": auth.tenant_id,
        "count": len(rows),
        "schedules": [_serialize_schedule(row) for row in rows],
        "execution_enabled": False,
    }
