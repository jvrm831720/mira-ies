"""Human review workflow for persisted retention campaign proposals.

This wave never schedules or executes a campaign.
"""
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthContext, require_min_role
from app.db.session import get_db
from app.models.retention_campaign import (
    RetentionCampaignProposal,
    RetentionCampaignProposalAuditEvent,
)

router = APIRouter(
    prefix="/agents/retention/campaigns/intelligence/proposals",
    tags=["Fluxo de Revisão de Campanhas"],
)
_EDITABLE_FIELDS = ("title", "objective", "strategy", "recommended_channels", "cadence_days", "message_brief")
_ALLOWED_CHANNELS = {"email", "whatsapp", "sms", "operacao_interna"}


class ProposalEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, min_length=3, max_length=160)
    objective: str | None = Field(default=None, min_length=3, max_length=4000)
    strategy: str | None = Field(default=None, min_length=3, max_length=4000)
    recommended_channels: list[str] | None = Field(default=None, max_length=4)
    cadence_days: list[int] | None = Field(default=None, max_length=12)
    message_brief: str | None = Field(default=None, min_length=3, max_length=8000)


class ReviewNote(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note: str = Field(min_length=3, max_length=2000)


class AuthorizationAttestation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    basis: str = Field(min_length=3, max_length=120)
    evidence_reference: str = Field(min_length=2, max_length=160)
    attestation: bool


def _require_human_user(auth: AuthContext) -> str:
    if not auth.user_id or auth.aal < 2:
        raise HTTPException(status_code=403, detail="Esta ação exige uma sessão humana com MFA (AAL2).")
    return auth.user_id


async def _get_proposal(db: AsyncSession, auth: AuthContext, proposal_id: str, *, lock: bool = False):
    query = select(RetentionCampaignProposal).where(
        RetentionCampaignProposal.id == proposal_id,
        RetentionCampaignProposal.tenant_id == auth.tenant_id,
    )
    if lock:
        query = query.with_for_update()
    proposal = (await db.execute(query)).scalar_one_or_none()
    if proposal is None:
        raise HTTPException(status_code=404, detail="Proposta não encontrada.")
    return proposal


def _serialize(proposal: RetentionCampaignProposal) -> dict[str, Any]:
    return {
        "id": proposal.id,
        "tenant_id": proposal.tenant_id,
        "status": proposal.status,
        "revision": proposal.revision,
        "title": proposal.title,
        "objective": proposal.objective,
        "strategy": proposal.strategy,
        "recommended_channels": proposal.recommended_channels,
        "cadence_days": proposal.cadence_days,
        "message_brief": proposal.message_brief,
        "source_group_ids": proposal.source_group_ids,
        "source_catalog_version": proposal.source_catalog_version,
        "recommendation_engine": proposal.recommendation_engine,
        "source_evaluated_at": proposal.source_evaluated_at,
        "audience_total": proposal.audience_total,
        "outreach_eligible_count": proposal.outreach_eligible_count,
        "blocked_count": proposal.blocked_count,
        "internal_action_count": proposal.internal_action_count,
        "audience_hash": proposal.audience_hash,
        "audience_snapshot": proposal.audience_snapshot,
        "created_by": proposal.created_by,
        "created_at": proposal.created_at,
        "updated_at": proposal.updated_at,
        "reviewed_by": proposal.reviewed_by,
        "reviewed_at": proposal.reviewed_at,
        "approved_by": proposal.approved_by,
        "approved_at": proposal.approved_at,
        "authorization_status": proposal.authorization_status,
        "authorization_basis": proposal.authorization_basis,
        "authorization_reference": proposal.authorization_reference,
        "authorization_attested_by": proposal.authorization_attested_by,
        "authorization_attested_at": proposal.authorization_attested_at,
        "execution_enabled": False,
    }


def _audit(db: AsyncSession, proposal: RetentionCampaignProposal, actor_id: str, event_type: str, details: dict):
    db.add(RetentionCampaignProposalAuditEvent(
        tenant_id=proposal.tenant_id,
        proposal_id=proposal.id,
        actor_user_id=actor_id,
        event_type=event_type,
        revision=proposal.revision,
        details=details,
    ))


@router.patch("/{proposal_id}")
async def edit_proposal(
    proposal_id: str,
    body: ProposalEdit,
    auth: AuthContext = Depends(require_min_role("coordinator")),
    db: AsyncSession = Depends(get_db),
):
    actor_id = _require_human_user(auth)
    proposal = await _get_proposal(db, auth, proposal_id, lock=True)
    if proposal.status not in {"draft", "changes_requested"}:
        raise HTTPException(status_code=409, detail="Somente propostas em rascunho ou com ajustes solicitados podem ser editadas.")
    changes = {}
    for field in _EDITABLE_FIELDS:
        if field not in body.model_fields_set:
            continue
        value = getattr(body, field)
        if isinstance(value, str):
            value = value.strip()
        if value is None:
            raise HTTPException(status_code=422, detail=f"O campo {field} não pode ser nulo.")
        if field == "recommended_channels":
            if len(set(value)) != len(value) or not set(value).issubset(_ALLOWED_CHANNELS):
                raise HTTPException(status_code=422, detail="Canais inválidos ou duplicados.")
            if "operacao_interna" in value and len(value) > 1:
                raise HTTPException(status_code=422, detail="Operação interna não pode ser combinada com canais de contato.")
        if field == "cadence_days":
            if any(day < 0 or day > 90 for day in value) or value != sorted(set(value)):
                raise HTTPException(status_code=422, detail="Cadência deve conter dias únicos, crescentes, entre 0 e 90.")
        old_value = getattr(proposal, field)
        if old_value != value:
            changes[field] = {"before": old_value, "after": value}
            setattr(proposal, field, value)
    if not changes:
        raise HTTPException(status_code=422, detail="Informe ao menos uma alteração.")
    proposal.revision += 1
    proposal.status = "draft"
    proposal.reviewed_by = None
    proposal.reviewed_at = None
    proposal.approved_by = None
    proposal.approved_at = None
    proposal.authorization_status = "not_verified"
    proposal.authorization_basis = None
    proposal.authorization_reference = None
    proposal.authorization_attested_by = None
    proposal.authorization_attested_at = None
    proposal.updated_at = datetime.now(timezone.utc)
    _audit(db, proposal, actor_id, "proposal.edited", {"changes": changes})
    await db.commit()
    await db.refresh(proposal)
    return _serialize(proposal)


@router.post("/{proposal_id}/review")
async def submit_for_review(
    proposal_id: str,
    auth: AuthContext = Depends(require_min_role("coordinator")),
    db: AsyncSession = Depends(get_db),
):
    actor_id = _require_human_user(auth)
    proposal = await _get_proposal(db, auth, proposal_id, lock=True)
    if proposal.status not in {"draft", "changes_requested"}:
        raise HTTPException(status_code=409, detail="A proposta não está disponível para revisão.")
    if actor_id == proposal.created_by:
        raise HTTPException(status_code=403, detail="O criador não pode atuar como revisor da própria proposta.")
    proposal.status = "in_review"
    proposal.reviewed_by = actor_id
    proposal.reviewed_at = datetime.now(timezone.utc)
    proposal.approved_by = None
    proposal.approved_at = None
    proposal.authorization_status = "not_verified"
    proposal.authorization_basis = None
    proposal.authorization_reference = None
    proposal.authorization_attested_by = None
    proposal.authorization_attested_at = None
    proposal.revision += 1
    proposal.updated_at = datetime.now(timezone.utc)
    _audit(db, proposal, actor_id, "proposal.submitted_for_review", {})
    await db.commit()
    await db.refresh(proposal)
    return _serialize(proposal)


@router.post("/{proposal_id}/request-changes")
async def request_proposal_changes(
    proposal_id: str,
    body: ReviewNote,
    auth: AuthContext = Depends(require_min_role("coordinator")),
    db: AsyncSession = Depends(get_db),
):
    actor_id = _require_human_user(auth)
    proposal = await _get_proposal(db, auth, proposal_id, lock=True)
    if proposal.status != "in_review":
        raise HTTPException(status_code=409, detail="Somente propostas em revisão podem receber solicitação de ajustes.")
    if actor_id == proposal.created_by:
        raise HTTPException(status_code=403, detail="O criador não pode revisar a própria proposta.")
    note = body.note.strip()
    if not note:
        raise HTTPException(status_code=422, detail="A justificativa não pode ficar vazia.")
    proposal.status = "changes_requested"
    proposal.revision += 1
    proposal.updated_at = datetime.now(timezone.utc)
    _audit(db, proposal, actor_id, "proposal.changes_requested", {"note": note})
    await db.commit()
    await db.refresh(proposal)
    return _serialize(proposal)


@router.post("/{proposal_id}/authorization-attestation")
async def attest_communication_authorization(
    proposal_id: str,
    body: AuthorizationAttestation,
    auth: AuthContext = Depends(require_min_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    actor_id = _require_human_user(auth)
    if not body.attestation:
        raise HTTPException(status_code=422, detail="A instituição deve confirmar expressamente a declaração.")
    proposal = await _get_proposal(db, auth, proposal_id, lock=True)
    if proposal.status != "in_review":
        raise HTTPException(status_code=409, detail="A autorização só pode ser atestada durante a revisão.")
    if actor_id == proposal.created_by:
        raise HTTPException(status_code=403, detail="O criador não pode atestar a autorização da própria proposta.")
    basis = body.basis.strip()
    evidence_reference = body.evidence_reference.strip()
    if not basis or not evidence_reference:
        raise HTTPException(status_code=422, detail="Base e referência documental não podem ficar vazias.")
    proposal.authorization_status = "institution_attested"
    proposal.authorization_basis = basis
    proposal.authorization_reference = evidence_reference
    proposal.authorization_attested_by = actor_id
    proposal.authorization_attested_at = datetime.now(timezone.utc)
    proposal.revision += 1
    proposal.updated_at = datetime.now(timezone.utc)
    _audit(db, proposal, actor_id, "proposal.communication_authorization_attested", {
        "basis": proposal.authorization_basis,
        "evidence_reference": proposal.authorization_reference,
        "meaning": "institution_assertion_not_legal_validation",
    })
    await db.commit()
    await db.refresh(proposal)
    return _serialize(proposal)


@router.post("/{proposal_id}/approve")
async def approve_proposal(
    proposal_id: str,
    auth: AuthContext = Depends(require_min_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    actor_id = _require_human_user(auth)
    proposal = await _get_proposal(db, auth, proposal_id, lock=True)
    if proposal.status != "in_review":
        raise HTTPException(status_code=409, detail="Somente propostas em revisão podem ser aprovadas.")
    if actor_id == proposal.created_by:
        raise HTTPException(status_code=403, detail="O criador não pode aprovar a própria proposta.")
    if proposal.authorization_status != "institution_attested" or not proposal.authorization_attested_by:
        raise HTTPException(status_code=409, detail="A autorização de comunicação ainda não foi atestada pela instituição.")
    if proposal.authorization_attested_by == proposal.created_by:
        raise HTTPException(status_code=409, detail="A declaração de autorização não pode ser feita pelo criador da proposta.")
    proposal.status = "approved"
    proposal.approved_by = actor_id
    proposal.approved_at = datetime.now(timezone.utc)
    proposal.revision += 1
    proposal.updated_at = datetime.now(timezone.utc)
    _audit(db, proposal, actor_id, "proposal.approved", {
        "authorization_status": proposal.authorization_status,
        "authorization_basis": proposal.authorization_basis,
        "authorization_reference": proposal.authorization_reference,
        "execution_enabled": False,
    })
    await db.commit()
    await db.refresh(proposal)
    return _serialize(proposal)


@router.get("/{proposal_id}/audit")
async def list_proposal_audit(
    proposal_id: str,
    auth: AuthContext = Depends(require_min_role("coordinator")),
    db: AsyncSession = Depends(get_db),
):
    _require_human_user(auth)
    proposal = await _get_proposal(db, auth, proposal_id)
    rows = list((await db.execute(
        select(RetentionCampaignProposalAuditEvent)
        .where(
            RetentionCampaignProposalAuditEvent.tenant_id == auth.tenant_id,
            RetentionCampaignProposalAuditEvent.proposal_id == proposal.id,
        )
        .order_by(RetentionCampaignProposalAuditEvent.created_at, RetentionCampaignProposalAuditEvent.id)
    )).scalars().all())
    return {
        "proposal_id": proposal.id,
        "count": len(rows),
        "events": [{
            "id": row.id,
            "event_type": row.event_type,
            "actor_user_id": row.actor_user_id,
            "revision": row.revision,
            "details": row.details,
            "created_at": row.created_at,
        } for row in rows],
    }
