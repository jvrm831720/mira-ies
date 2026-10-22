"""Safe bridge from campaign rules to the existing retention orchestrator."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.orchestrator import RetentionOrchestrator
from app.core.auth import AuthContext, require_min_role
from app.db.session import get_db
from app.models.intervention import InterventionLog
from app.models.retention_campaign import RetentionCampaign
from app.api.retention_campaigns import _evaluate, _get

router = APIRouter(prefix="/agents/retention/campaigns", tags=["Campanhas de Retenção"])


@router.post("/{campaign_id}/run-dry-run")
async def run_dry_run(campaign_id: str, limit: int = Query(200, ge=1, le=500),
                      student_ids: list[str] | None = Query(None),
                      auth: AuthContext = Depends(require_min_role("operator")),
                      db: AsyncSession = Depends(get_db)):
    """Aplica regras e passa elegíveis pelo orquestrador, sempre sem envio real."""
    campaign = await _get(db, auth.tenant_id, campaign_id)
    if campaign.status != "active":
        raise HTTPException(status_code=409, detail="Ative a campanha antes de executar.")
    decisions = await _evaluate(db, campaign, limit, student_ids)
    groups = {}
    rules_by_student = {}
    for item in decisions:
        if not item["eligible"]:
            continue
        rules_by_student[item["student_id"]] = item["matched_rules"]
        for channel in {hit["action"]["channel"] for hit in item["matched_rules"]}:
            key = (channel, item["risk_level"])
            groups.setdefault(key, [])
            if item["student_id"] not in groups[key]:
                groups[key].append(item["student_id"])
    executions = []
    for (channel, risk_level), ids in groups.items():
        runner = RetentionOrchestrator(db, tenant_id=auth.tenant_id)
        result = await runner.run(
            risk_levels=[risk_level], limit=min(limit, 500), dry_run=True,
            channels=[channel], campaign_id=campaign.id,
            idempotency_key=f"campaign:{campaign.id}:v{campaign.version}:{datetime.now(timezone.utc).date()}:{channel}:{risk_level}",
            student_ids=ids,
        )
        executions.append({"channel": channel, "risk_level": risk_level, **result})
        logs = await db.execute(select(InterventionLog).where(
            InterventionLog.tenant_id == auth.tenant_id,
            InterventionLog.campaign_id == campaign.id,
            InterventionLog.student_id.in_(ids)
        ).order_by(InterventionLog.created_at.desc()).limit(len(ids) * 10))
        for log in logs.scalars().all():
            hits = rules_by_student.get(log.student_id, [])
            if not hits or log.status == "skipped":
                continue
            context = dict(log.decision_context or {})
            context["campaign_version"] = campaign.version
            context["matched_rules"] = hits
            log.decision_context = context
            log.decision_reason = ((log.decision_reason or "") + "; rules=" +
                                   ",".join(h["rule_id"] + ":v" + str(h["rule_version"]) for h in hits))[:240]
        await db.commit()
    return {"campaign_id": campaign.id, "campaign_version": campaign.version,
            "dry_run": True, "students_evaluated": len(decisions),
            "eligible": sum(x["eligible"] for x in decisions),
            "skipped": sum(not x["eligible"] for x in decisions),
            "decisions": decisions, "execution": executions,
            "message": "Dry-run concluído. Nenhuma mensagem real foi enviada."}
