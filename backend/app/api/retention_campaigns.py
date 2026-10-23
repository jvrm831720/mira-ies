"""CRUD and safe simulation for tenant-scoped retention campaigns."""
from datetime import datetime, timezone
import math
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.channels.email import is_valid_email
from app.agents.channels.whatsapp import normalize_phone_br
from app.agents.campaign_templates import validate_campaign_template
from app.agents.rule_engine import RuleValidationError, evaluate_rules, validate_rule
from app.core.auth import AuthContext, get_current_tenant, require_min_role
from app.db.session import get_db
from app.models.intervention import InterventionLog
from app.models.retention_campaign import RetentionCampaign
from app.models.student import Student

router = APIRouter(prefix="/agents/retention/campaigns", tags=["Campanhas de Retenção"])

_VALID_RISK_LEVELS = frozenset({"baixo", "medio", "critico"})


def _has_complete_risk_data(student: Student) -> bool:
    """Retorna False se o snapshot de risco estiver ausente ou fora do contrato."""
    risk_level = student.risk_level
    risk_score = student.risk_score
    if risk_level not in _VALID_RISK_LEVELS:
        return False
    if isinstance(risk_score, bool) or not isinstance(risk_score, (int, float)):
        return False
    return math.isfinite(risk_score) and 0 <= risk_score <= 100


class CampaignInput(BaseModel):
    slug: str = Field(min_length=2, max_length=100, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    name: str = Field(min_length=2, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    rules: list[dict[str, Any]] = Field(min_length=1, max_length=30)


class StatusInput(BaseModel):
    status: str = Field(pattern=r"^(active|paused|draft)$")


def _validate(rules):
    seen = set()
    for rule in rules:
        try:
            validate_rule(rule)
            validate_campaign_template(rule["action"]["channel"], rule["action"]["template_id"])
        except (RuleValidationError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if rule["id"] in seen:
            raise HTTPException(status_code=422, detail=f"ID de regra duplicado: {rule['id']}")
        seen.add(rule["id"])


def _serialize(c):
    return {"id": c.id, "tenant_id": c.tenant_id, "slug": c.slug, "name": c.name,
            "description": c.description, "version": c.version, "status": c.status,
            "rules": c.rules, "created_at": c.created_at, "updated_at": c.updated_at,
            "activated_at": c.activated_at}


async def _get(db, tenant_id, campaign_id):
    result = await db.execute(select(RetentionCampaign).where(
        RetentionCampaign.id == campaign_id,
        RetentionCampaign.tenant_id == tenant_id,
        RetentionCampaign.archived.is_(False)))
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campanha não encontrada.")
    return campaign


async def _evaluate(db, campaign, limit, student_ids=None):
    query = select(Student).where(Student.tenant_id == campaign.tenant_id, Student.is_active.is_(True))
    if student_ids:
        query = query.where(Student.id.in_(student_ids))
    students = list((await db.execute(query.order_by(Student.updated_at.desc()).limit(limit))).scalars().all())
    if not students:
        return []
    ids = [s.id for s in students]
    rows = await db.execute(select(InterventionLog.student_id, func.max(InterventionLog.created_at)).where(
        InterventionLog.tenant_id == campaign.tenant_id,
        InterventionLog.student_id.in_(ids),
        InterventionLog.status.in_(["sent", "dry_run", "sending", "unknown"])
    ).group_by(InterventionLog.student_id))
    last = dict(rows.all())
    now = datetime.now(timezone.utc)
    output = []
    for s in students:
        contacted = last.get(s.id)
        facts = {"risk_level": s.risk_level, "risk_score": s.risk_score,
                 "days_since_contact": max(0, (now-contacted).days) if contacted else 36500,
                 "opt_out": bool(s.communication_opt_out), "has_phone": bool(s.telefone),
                 "has_email": bool(s.email)}
        risk_data_complete = _has_complete_risk_data(s)
        decisions = evaluate_rules(campaign.rules, facts)
        winner = next((decision for decision in decisions if decision.matched), None)
        blocked = (
            "communication_opt_out" if facts["opt_out"] else
            "missing_risk_data" if not risk_data_complete else
            "missing_contact" if not facts["has_phone"] and not facts["has_email"] else
            None
        )
        if not blocked and winner:
            channel = winner.action["channel"]
            if channel == "email" and not is_valid_email(s.email):
                blocked = "missing_email"
            elif channel in {"whatsapp", "sms"} and not normalize_phone_br(s.telefone):
                blocked = "missing_phone"

        selected = winner if not blocked else None
        selected_rule = None
        hits = []
        if selected:
            selected_rule = {
                "rule_id": selected.rule_id,
                "rule_version": selected.rule_version,
                "priority": selected.priority,
                "reason": selected.reason,
                "action": selected.action,
            }
            hits = [selected_rule]
        evaluated_rules = [
            {
                "rule_id": decision.rule_id,
                "rule_version": decision.rule_version,
                "priority": decision.priority,
                "matched": decision.matched,
                "selected": bool(selected and decision.rule_id == selected.rule_id),
                "reason": decision.reason,
                "action": decision.action,
            }
            for decision in decisions
        ]
        reasons = (
            [f"Bloqueio de segurança: {blocked}"] if blocked else
            [selected.reason] if selected else
            [decision.reason for decision in decisions]
        )
        output.append({
            "student_id": s.id,
            "matricula": s.matricula,
            "risk_level": facts["risk_level"],
            "risk_score": facts["risk_score"],
            "days_since_contact": facts["days_since_contact"],
            "eligible": selected is not None,
            "selected_rule": selected_rule,
            "matched_rules": hits,
            "rule_evaluations": evaluated_rules,
            "blocked_reason": blocked,
            "reasons": reasons,
        })
    return output


@router.post("", status_code=201)
async def create_campaign(body: CampaignInput, auth: AuthContext = Depends(require_min_role("coordinator")),
                          db: AsyncSession = Depends(get_db)):
    _validate(body.rules)
    exists = await db.execute(select(RetentionCampaign.id).where(
        RetentionCampaign.tenant_id == auth.tenant_id, RetentionCampaign.slug == body.slug,
        RetentionCampaign.version == 1))
    if exists.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Já existe campanha com esse slug e versão.")
    c = RetentionCampaign(tenant_id=auth.tenant_id, slug=body.slug, name=body.name,
                          description=body.description, version=1, status="draft", rules=body.rules,
                          created_by=auth.user_id)
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return _serialize(c)


@router.get("")
async def list_campaigns(status: str | None = Query(None, pattern=r"^(draft|active|paused)$"),
                         auth: AuthContext = Depends(get_current_tenant), db: AsyncSession = Depends(get_db)):
    query = select(RetentionCampaign).where(RetentionCampaign.tenant_id == auth.tenant_id,
                                            RetentionCampaign.archived.is_(False))
    if status:
        query = query.where(RetentionCampaign.status == status)
    rows = list((await db.execute(query.order_by(RetentionCampaign.slug,
                                                  RetentionCampaign.version.desc()))).scalars().all())
    latest = {}
    for c in rows:
        latest.setdefault(c.slug, c)
    return {"count": len(latest), "campaigns": [_serialize(c) for c in latest.values()]}


@router.get("/{campaign_id}")
async def get_campaign(campaign_id: str, auth: AuthContext = Depends(get_current_tenant),
                       db: AsyncSession = Depends(get_db)):
    return _serialize(await _get(db, auth.tenant_id, campaign_id))


@router.post("/{campaign_id}/versions", status_code=201)
async def new_version(campaign_id: str, body: CampaignInput,
                      auth: AuthContext = Depends(require_min_role("coordinator")),
                      db: AsyncSession = Depends(get_db)):
    old = await _get(db, auth.tenant_id, campaign_id)
    if body.slug != old.slug:
        raise HTTPException(status_code=422, detail="A nova versão deve manter o slug da campanha.")
    _validate(body.rules)
    result = await db.execute(select(func.max(RetentionCampaign.version)).where(
        RetentionCampaign.tenant_id == auth.tenant_id, RetentionCampaign.slug == old.slug))
    version = int(result.scalar_one() or old.version) + 1
    c = RetentionCampaign(tenant_id=auth.tenant_id, slug=old.slug, name=body.name,
                          description=body.description, version=version, status="draft",
                          rules=body.rules, created_by=auth.user_id)
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return _serialize(c)


@router.patch("/{campaign_id}/status")
async def set_status(campaign_id: str, body: StatusInput,
                     auth: AuthContext = Depends(require_min_role("coordinator")),
                     db: AsyncSession = Depends(get_db)):
    c = await _get(db, auth.tenant_id, campaign_id)
    now = datetime.now(timezone.utc)
    if body.status == "active":
        _validate(c.rules)
        # Troca de versão numa única transação; o índice parcial no banco é a
        # última barreira contra ativações concorrentes.
        await db.execute(update(RetentionCampaign).where(
            RetentionCampaign.tenant_id == auth.tenant_id,
            RetentionCampaign.slug == c.slug,
            RetentionCampaign.id != c.id,
            RetentionCampaign.status == "active",
            RetentionCampaign.archived.is_(False),
        ).values(status="paused", updated_at=now))
        c.activated_at = now
    c.status = body.status
    c.updated_at = now
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        constraint_name = (
            getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
            or getattr(exc.orig, "constraint_name", None)
        )
        if constraint_name == "uq_retention_campaigns_one_active_version":
            raise HTTPException(
                status_code=409,
                detail="Outra versão desta campanha foi ativada simultaneamente. Recarregue e tente novamente.",
            ) from exc
        raise
    await db.refresh(c)
    return _serialize(c)


@router.post("/{campaign_id}/simulate")
async def simulate(campaign_id: str, limit: int = Query(200, ge=1, le=500),
                   student_ids: list[str] | None = Query(None),
                   auth: AuthContext = Depends(get_current_tenant), db: AsyncSession = Depends(get_db)):
    c = await _get(db, auth.tenant_id, campaign_id)
    decisions = await _evaluate(db, c, limit, student_ids)
    return {"campaign_id": c.id, "version": c.version, "simulation": True,
            "students_evaluated": len(decisions), "eligible": sum(x["eligible"] for x in decisions),
            "skipped": sum(not x["eligible"] for x in decisions), "decisions": decisions}
