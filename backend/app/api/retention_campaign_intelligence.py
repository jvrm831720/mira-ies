"""Explainable campaign opportunities and persisted draft proposals."""
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.channels.email import is_valid_email
from app.agents.channels.whatsapp import normalize_phone_br
from app.api.student_groups import _build_summary
from app.core.auth import AuthContext, get_current_tenant, require_min_role
from app.db.session import get_db
from app.models.intervention import InterventionLog
from app.models.retention_campaign import RetentionCampaignProposal
from app.models.student import Student
from app.services.campaign_opportunities import build_campaign_opportunities
from app.services.campaign_proposals import deduplicate_audience_members, hash_audience_snapshot
from app.services.consent import is_communication_allowed
from app.student_groups.catalog import GROUP_CATALOG_VERSION, get_group_definition
from app.student_groups.evaluate import evaluate_student_groups
from app.student_groups.loading import GROUP_MAX_STUDENTS, iter_student_group_batches, student_snapshot

router = APIRouter(
    prefix="/agents/retention/campaigns/intelligence",
    tags=["Inteligência de Campanhas"],
)
RECENT_CONTACT_DAYS = 7
_CONTACT_STATUSES = ("sent", "sending", "unknown")


class ProposalInput(BaseModel):
    group_ids: list[str] = Field(min_length=1, max_length=7)


def _serialize_proposal(proposal: RetentionCampaignProposal) -> dict[str, Any]:
    return {
        "id": proposal.id,
        "tenant_id": proposal.tenant_id,
        "status": proposal.status,
        "title": proposal.title,
        "source_group_ids": proposal.source_group_ids,
        "source_catalog_version": proposal.source_catalog_version,
        "recommendation_engine": proposal.recommendation_engine,
        "source_evaluated_at": proposal.source_evaluated_at,
        "objective": proposal.objective,
        "strategy": proposal.strategy,
        "recommended_channels": proposal.recommended_channels,
        "cadence_days": proposal.cadence_days,
        "message_brief": proposal.message_brief,
        "audience_snapshot": proposal.audience_snapshot,
        "audience_hash": proposal.audience_hash,
        "audience_total": proposal.audience_total,
        "outreach_eligible_count": proposal.outreach_eligible_count,
        "blocked_count": proposal.blocked_count,
        "internal_action_count": proposal.internal_action_count,
        "created_by": proposal.created_by,
        "created_at": proposal.created_at,
        "updated_at": proposal.updated_at,
        "execution_enabled": False,
        "communication_authorization_status": "not_verified",
        "authorization_review_required": True,
    }


@router.get("/opportunities")
async def list_campaign_opportunities(
    auth: AuthContext = Depends(require_min_role("coordinator")),
    db: AsyncSession = Depends(get_db),
):
    summary = await _build_summary(db, tenant_id=auth.tenant_id, evaluated_at=datetime.now(timezone.utc))
    opportunities = build_campaign_opportunities(summary)
    return {
        "tenant_id": auth.tenant_id,
        "generated_at": summary["evaluated_at"],
        "catalog_version": GROUP_CATALOG_VERSION,
        "recommendation_engine": "signals-and-rules-v1",
        "is_ai_generated_copy": False,
        "students_evaluated": summary["evaluated"],
        "total_active_students": summary["total_eligible"],
        "truncated": summary["truncated"],
        "opportunities_count": len(opportunities),
        "opportunities": opportunities,
        "notes": [
            "Grupos podem se sobrepor; não some suas contagens como audiência única.",
            "Alcance bruto não desconta contato inválido, opt-out, preferências ou intervenções recentes.",
            "Sem score é ação interna de saneamento e não autoriza contato.",
            "Nenhuma campanha é aprovada, agendada ou executada nesta etapa.",
            "Elegibilidade técnica de contato não comprova consentimento nem base legal; a autorização de comunicação permanece não verificada e exige revisão da instituição.",
        ],
    }


@router.post("/proposals", status_code=201)
async def create_campaign_proposal(
    body: ProposalInput,
    auth: AuthContext = Depends(require_min_role("coordinator")),
    db: AsyncSession = Depends(get_db),
):
    group_ids = list(dict.fromkeys(body.group_ids))
    if len(group_ids) != len(body.group_ids):
        raise HTTPException(status_code=422, detail="Não repita grupos na proposta.")
    definitions = {group_id: get_group_definition(group_id) for group_id in group_ids}
    if any(definition is None for definition in definitions.values()):
        raise HTTPException(status_code=422, detail="A proposta contém grupo desconhecido.")

    evaluated_at = datetime.now(timezone.utc)
    summary = await _build_summary(db, tenant_id=auth.tenant_id, evaluated_at=evaluated_at)
    if summary["truncated"] or summary["evaluated"] != summary["total_eligible"]:
        raise HTTPException(
            status_code=409,
            detail="A avaliação excedeu o limite de cobertura. Não é seguro persistir um snapshot parcial de audiência.",
        )
    recommendations = {
        item["group_id"]: item
        for item in build_campaign_opportunities(summary)
        if item["group_id"] in group_ids
    }
    if any(group_id not in recommendations for group_id in group_ids):
        raise HTTPException(status_code=409, detail="Um ou mais grupos selecionados não possuem oportunidade confirmada.")

    # Re-evaluate all active students in one bounded, tenant-scoped pass. The
    # proposal is rejected rather than persisting a partial audience.
    raw_members: list[dict[str, Any]] = []
    total_seen = 0
    matched_counts = {group_id: 0 for group_id in group_ids}
    expected_counts = {
        item["id"]: item["matched_count"]
        for item in summary["groups"]
        if item["id"] in group_ids
    }
    cutoff = evaluated_at - timedelta(days=RECENT_CONTACT_DAYS)
    async for batch in iter_student_group_batches(
        db, tenant_id=auth.tenant_id, max_students=GROUP_MAX_STUDENTS
    ):
        total_seen += len(batch.students)
        ids = [student.id for student in batch.students]
        full_students = list(
            (
                await db.execute(
                    select(Student).where(Student.tenant_id == auth.tenant_id, Student.id.in_(ids))
                )
            ).scalars().all()
        )
        by_id = {student.id: student for student in full_students}
        recent_rows = await db.execute(
            select(InterventionLog.student_id, func.max(InterventionLog.created_at))
            .where(
                InterventionLog.tenant_id == auth.tenant_id,
                InterventionLog.student_id.in_(ids),
                InterventionLog.status.in_(_CONTACT_STATUSES),
                InterventionLog.created_at >= cutoff,
            )
            .group_by(InterventionLog.student_id)
        )
        recent_by_student = dict(recent_rows.all())
        for snapshot in batch.students:
            result = evaluate_student_groups(
                student_id=snapshot.id,
                tenant_id=auth.tenant_id,
                student=student_snapshot(snapshot),
                assessments=batch.assessments_by_student.get(snapshot.id, []),
                history_unavailable=batch.history_unavailable,
                evaluated_at=evaluated_at,
            )
            matched = sorted(
                group.group_id for group in result.groups
                if group.group_id in group_ids and group.state == "TRUE"
            )
            for group_id in matched:
                matched_counts[group_id] += 1
            if not matched:
                continue
            student = by_id.get(snapshot.id)
            if student is None:
                raise HTTPException(status_code=409, detail="A audiência mudou durante a avaliação; gere a proposta novamente.")
            outreach_groups = [group_id for group_id in matched if group_id != "missing_score"]
            internal_only = not outreach_groups
            allowed_channels: set[str] = set()
            blocked_reasons: set[str] = set()
            recent_at = recent_by_student.get(student.id)
            if internal_only:
                blocked_reasons.add("internal_data_quality_action")
            elif student.communication_opt_out:
                blocked_reasons.add("global_opt_out")
            elif recent_at is not None:
                blocked_reasons.add("recent_intervention")
            else:
                candidate_channels = {
                    channel
                    for group_id in outreach_groups
                    for channel in recommendations[group_id]["recommended_channels"]
                }
                for channel in sorted(candidate_channels):
                    if not is_communication_allowed(student, channel, "retention"):
                        blocked_reasons.add(f"preference_blocked:{channel}")
                        continue
                    if channel == "email" and not is_valid_email(student.email):
                        blocked_reasons.add("invalid_email")
                        continue
                    if channel in {"whatsapp", "sms"} and not normalize_phone_br(student.telefone):
                        blocked_reasons.add(f"invalid_{channel}_contact")
                        continue
                    allowed_channels.add(channel)
                if not allowed_channels and not blocked_reasons:
                    blocked_reasons.add("no_permitted_channel")
            raw_members.append({
                "student_id": student.id,
                "matched_group_ids": matched,
                "global_opt_out": bool(student.communication_opt_out),
                "eligible_channels": sorted(allowed_channels),
                "blocked_reasons": sorted(blocked_reasons),
                "internal_action_only": internal_only,
                "recent_intervention_at": recent_at.isoformat() if recent_at else None,
                "contact_validity": {
                    "email": bool(is_valid_email(student.email)),
                    "whatsapp": bool(normalize_phone_br(student.telefone)),
                },
            })

    if total_seen != summary["total_eligible"] or matched_counts != expected_counts:
        raise HTTPException(status_code=409, detail="A audiência mudou durante a avaliação; gere a proposta novamente.")
    snapshot = deduplicate_audience_members(raw_members)
    if not snapshot:
        raise HTTPException(status_code=409, detail="Nenhum aluno confirmado nos grupos selecionados.")

    all_recommendations = [recommendations[group_id] for group_id in group_ids]
    objectives = list(dict.fromkeys(item["objective"] for item in all_recommendations))
    strategies = list(dict.fromkeys(item["strategy"] for item in all_recommendations))
    message_briefs = list(dict.fromkeys(item["message_brief"] for item in all_recommendations))
    channels = sorted({
        channel for item in all_recommendations for channel in item["recommended_channels"]
        if channel != "operacao_interna"
    })
    cadence = sorted({day for item in all_recommendations for day in item["cadence_days"]})
    eligible_count = sum(bool(item["eligible_channels"]) for item in snapshot)
    internal_count = sum(bool(item["internal_action_only"]) for item in snapshot)
    blocked_count = len(snapshot) - eligible_count - internal_count

    proposal = RetentionCampaignProposal(
        tenant_id=auth.tenant_id,
        status="draft",
        title=("Proposta: " + " + ".join(definitions[group_id].name for group_id in group_ids))[:160],
        source_group_ids=group_ids,
        source_catalog_version=GROUP_CATALOG_VERSION,
        recommendation_engine="signals-and-rules-v1",
        source_evaluated_at=evaluated_at,
        objective=" ".join(objectives),
        strategy=" ".join(strategies),
        recommended_channels=channels,
        cadence_days=cadence,
        message_brief=" ".join(message_briefs),
        audience_snapshot=snapshot,
        audience_hash=hash_audience_snapshot(snapshot),
        audience_total=len(snapshot),
        outreach_eligible_count=eligible_count,
        blocked_count=blocked_count,
        internal_action_count=internal_count,
        created_by=auth.user_id,
    )
    db.add(proposal)
    await db.commit()
    await db.refresh(proposal)
    return _serialize_proposal(proposal)


@router.get("/proposals")
async def list_campaign_proposals(
    auth: AuthContext = Depends(require_min_role("coordinator")),
    db: AsyncSession = Depends(get_db),
):
    rows = list((await db.execute(
        select(RetentionCampaignProposal)
        .where(RetentionCampaignProposal.tenant_id == auth.tenant_id)
        .order_by(RetentionCampaignProposal.created_at.desc())
        .limit(100)
    )).scalars().all())
    return {"count": len(rows), "proposals": [_serialize_proposal(row) for row in rows]}


@router.get("/proposals/{proposal_id}")
async def get_campaign_proposal(
    proposal_id: str,
    auth: AuthContext = Depends(require_min_role("coordinator")),
    db: AsyncSession = Depends(get_db),
):
    proposal = (await db.execute(
        select(RetentionCampaignProposal).where(
            RetentionCampaignProposal.id == proposal_id,
            RetentionCampaignProposal.tenant_id == auth.tenant_id,
        )
    )).scalar_one_or_none()
    if proposal is None:
        raise HTTPException(status_code=404, detail="Proposta não encontrada.")
    return _serialize_proposal(proposal)
