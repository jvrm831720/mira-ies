"""Safe bridge from campaign rules to the existing retention orchestrator."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.orchestrator import RetentionOrchestrator
from app.core.auth import AuthContext, require_min_role
from app.db.session import get_db
from app.models.intervention import InterventionLog
from app.api.retention_campaigns import _evaluate, _get, _validate

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
    _validate(campaign.rules)
    decisions = await _evaluate(db, campaign, limit, student_ids)
    # Persiste decisões negativas com chave diária para não duplicar auditoria em retries.
    today = datetime.now(timezone.utc).date().isoformat()
    for item in decisions:
        if item["eligible"]:
            continue
        key = f"campaign-decision:{campaign.id}:v{campaign.version}:{item['student_id']}:{today}"
        existing = await db.execute(select(InterventionLog.id).where(
            InterventionLog.tenant_id == auth.tenant_id,
            InterventionLog.idempotency_key == key
        ))
        if existing.scalar_one_or_none():
            continue
        db.add(InterventionLog(
            tenant_id=auth.tenant_id,
            student_id=item["student_id"],
            matricula=item["matricula"],
            channel=None,
            risk_level=item["risk_level"],
            risk_score=item["risk_score"],
            status="skipped",
            skip_reason=item["blocked_reason"] or "rule_not_matched",
            decision_reason="; ".join(item["reasons"])[:240],
            decision_context={
                "campaign_version": campaign.version,
                "selected_rule": None,
                "evaluated_rules": item["rule_evaluations"],
                "days_since_contact": item["days_since_contact"],
                "blocked_reason": item["blocked_reason"],
            },
            campaign_id=campaign.id,
            idempotency_key=key,
            delivery_status="not_applicable",
        ))
    await db.commit()

    eligible_items = [item for item in decisions if item["eligible"]]
    campaign_actions: dict[str, dict] = {}
    for item in eligible_items:
        selected = item["selected_rule"]
        action = selected["action"]
        campaign_actions[item["student_id"]] = {
            "channel": action["channel"],
            "template_id": action["template_id"],
            "campaign_version": campaign.version,
            "rule_id": selected["rule_id"],
            "rule_version": selected["rule_version"],
            "priority": selected["priority"],
            "evaluated_rules": item["rule_evaluations"],
            "days_since_contact": item["days_since_contact"],
        }

    executions = []
    if campaign_actions:
        runner = RetentionOrchestrator(db, tenant_id=auth.tenant_id)
        channels = sorted({action["channel"] for action in campaign_actions.values()})
        risk_levels = sorted({item["risk_level"] for item in eligible_items if item["risk_level"]})
        result = await runner.run(
            risk_levels=risk_levels,
            limit=min(limit, 500),
            dry_run=True,
            channels=channels,
            campaign_id=campaign.id,
            idempotency_key=(
                f"campaign:{campaign.id}:v{campaign.version}:"
                f"{datetime.now(timezone.utc).date().isoformat()}"
            ),
            student_ids=list(campaign_actions),
            campaign_actions=campaign_actions,
        )
        executions.append({
            "channels": channels,
            "students_with_selected_action": len(campaign_actions),
            **result,
        })

    return {"campaign_id": campaign.id, "campaign_version": campaign.version,
            "dry_run": True, "students_evaluated": len(decisions),
            "eligible": sum(x["eligible"] for x in decisions),
            "skipped": sum(not x["eligible"] for x in decisions),
            "decisions": decisions, "execution": executions,
            "message": "Dry-run concluído. Nenhuma mensagem real foi enviada."}
