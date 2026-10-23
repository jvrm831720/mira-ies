"""CRUD and safe simulation for tenant-scoped retention campaigns."""
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.rule_engine import RuleValidationError, evaluate_rules, validate_rule
from app.core.auth import AuthContext, get_current_tenant, require_min_role
from app.db.session import get_db
from app.models.intervention import InterventionLog
from app.models.retention_campaign import RetentionCampaign
from app.models.student import Student

router = APIRouter(prefix="/agents/retention/campaigns", tags=["Campanhas de Retenção"])


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
        except RuleValidationError as exc:
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
        facts = {"risk_level": s.risk_level or "baixo", "risk_score": s.risk_score,
                 "days_since_contact": max(0, (now-contacted).days) if contacted else 36500,
                 "opt_out": bool(s.communication_opt_out), "has_phone": bool(s.telefone),
                 "has_email": bool(s.email)}
        decisions = evaluate_rules(campaign.rules, facts)
        hits = [{"rule_id": d.rule_id, "rule_version": d.rule_version,
                 "reason": d.reason, "action": d.action} for d in decisions if d.matched]
        blocked = "communication_opt_out" if facts["opt_out"] else (
            "missing_contact" if not facts["has_phone"] and not facts["has_email"] else None)
        if blocked:
            hits = []
        output.append({"student_id": s.id, "matricula": s.matricula, "risk_level": facts["risk_level"],
                       "risk_score": facts["risk_score"], "days_since_contact": facts["days_since_contact"],
                       "eligible": bool(hits), "matched_rules": hits, "blocked_reason": blocked,
                       "reasons": [h["reason"] for h in hits] if hits else
                       ([f"Bloqueio de segurança: {blocked}"] if blocked else [d.reason for d in decisions])})
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
    if body.status == "active":
        _validate(c.rules)
        c.activated_at = datetime.now(timezone.utc)
    c.status = body.status
    c.updated_at = datetime.now(timezone.utc)
    await db.commit()
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
