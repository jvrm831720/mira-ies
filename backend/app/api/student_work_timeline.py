"""Linha do tempo operacional do aluno — somente leitura, fontes reais."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthContext, require_min_role
from app.db.session import get_db
from app.models.engagement import StudentEngagementEvent
from app.models.intervention import InterventionLog
from app.models.risk_assessment import RiskAssessment
from app.models.student import Student
from app.models.work_activity import WorkActivity, WorkActivityEvent

router = APIRouter(tags=["Central de Trabalho"])


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value else None


@router.get("/students/{student_id}/work-timeline")
async def student_work_timeline(
    student_id: str,
    limit: int = Query(100, ge=1, le=500),
    auth: AuthContext = Depends(require_min_role("operator")),
    db: AsyncSession = Depends(get_db),
):
    """Agrega RiskAssessment, InterventionLog, WorkActivity, WorkActivityEvent e StudentEngagementEvent.

    Não inventa eventos; não mistura status de envio com conclusão de atividade.
    Ordenação: mais antigo primeiro (frontend pode inverter para leitura cronológica recente).
    """
    st = await db.execute(
        select(Student.id).where(
            Student.id == student_id, Student.tenant_id == auth.tenant_id
        )
    )
    if not st.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Aluno não encontrado.")

    items: list[dict[str, Any]] = []

    # Risk assessments
    try:
        risk_rows = (
            await db.execute(
                select(RiskAssessment)
                .where(
                    RiskAssessment.tenant_id == auth.tenant_id,
                    RiskAssessment.student_id == student_id,
                )
                .order_by(RiskAssessment.evaluated_at.desc())
                .limit(limit)
            )
        ).scalars().all()
        for r in risk_rows:
            items.append(
                {
                    "source": "risk_assessment",
                    "id": r.id,
                    "at": _iso(r.evaluated_at),
                    "summary": f"Avaliação de risco: {r.risk_level} (score {r.score})",
                    "refs": {
                        "risk_level": r.risk_level,
                        "score": r.score,
                        "model_version": getattr(r, "model_version", None),
                        "score_basis": getattr(r, "score_basis", None),
                    },
                }
            )
    except Exception:
        # Schema opcional: se tabela ausente, não inventar — apenas omitir fonte
        pass

    # Intervention logs
    log_rows = (
        await db.execute(
            select(InterventionLog)
            .where(
                InterventionLog.tenant_id == auth.tenant_id,
                InterventionLog.student_id == student_id,
            )
            .order_by(InterventionLog.created_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    for log in log_rows:
        channel = log.channel or "sem canal"
        parts = [f"Intervenção {log.status}", f"canal={channel}"]
        if log.delivery_status:
            parts.append(f"delivery={log.delivery_status}")
        if log.outcome:
            parts.append(f"outcome={log.outcome}")
        items.append(
            {
                "source": "intervention_log",
                "id": log.id,
                "at": _iso(log.created_at),
                "summary": "; ".join(parts),
                "refs": {
                    "status": log.status,
                    "delivery_status": log.delivery_status,
                    "outcome": log.outcome,
                    "channel": log.channel,
                    "decision_reason": log.decision_reason,
                    "campaign_id": log.campaign_id,
                },
            }
        )

    # Work activities (criação)
    act_rows = (
        await db.execute(
            select(WorkActivity)
            .where(
                WorkActivity.tenant_id == auth.tenant_id,
                WorkActivity.student_id == student_id,
            )
            .order_by(WorkActivity.created_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    activity_ids = [act.id for act in act_rows]
    for act in act_rows:
        items.append(
            {
                "source": "work_activity",
                "id": act.id,
                "at": _iso(act.created_at),
                "summary": f"Atividade [{act.status}] {act.title}",
                "refs": {
                    "status": act.status,
                    "activity_type": act.activity_type,
                    "title": act.title,
                    "assignee_user_id": act.assignee_user_id,
                    "intervention_log_id": act.intervention_log_id,
                    "due_at": _iso(act.due_at),
                    "completed_at": _iso(act.completed_at),
                    "event_type": "created",
                },
            }
        )

    # Work activity events (result_recorded, status changes, etc.) for student's activities
    if activity_ids:
        try:
            evt_rows = (
                await db.execute(
                    select(WorkActivityEvent)
                    .where(
                        WorkActivityEvent.tenant_id == auth.tenant_id,
                        WorkActivityEvent.activity_id.in_(activity_ids),
                    )
                    .order_by(WorkActivityEvent.created_at.desc())
                    .limit(limit)
                )
            ).scalars().all()
            act_by_id = {a.id: a for a in act_rows}
            for ev in evt_rows:
                # Skip pure "created" if we already emit activity creation
                if ev.event_type == "created":
                    continue
                act = act_by_id.get(ev.activity_id)
                title = act.title if act else "atividade"
                payload = ev.payload or {}
                if ev.event_type == "result_recorded":
                    kind = payload.get("kind") or ""
                    note = payload.get("note") or ""
                    summary = f"Resultado operacional: {kind or 'registrado'}"
                    if note:
                        summary += f" — {note[:120]}"
                elif ev.event_type in ("status_changed", "completed", "cancelled"):
                    summary = f"Atividade [{ev.event_type}] {title}"
                else:
                    summary = f"Atividade evento {ev.event_type}: {title}"
                items.append(
                    {
                        "source": "work_activity",
                        "id": ev.id,
                        "at": _iso(ev.created_at),
                        "summary": summary,
                        "refs": {
                            "activity_id": ev.activity_id,
                            "event_type": ev.event_type,
                            "payload": payload,
                            "title": title,
                            "status": act.status if act else None,
                            "intervention_log_id": act.intervention_log_id if act else None,
                        },
                    }
                )
        except Exception:
            pass

    # Engagement events
    try:
        eng_rows = (
            await db.execute(
                select(StudentEngagementEvent)
                .where(
                    StudentEngagementEvent.tenant_id == auth.tenant_id,
                    StudentEngagementEvent.student_id == student_id,
                )
                .order_by(StudentEngagementEvent.occurred_at.desc())
                .limit(limit)
            )
        ).scalars().all()
        for ev in eng_rows:
            items.append(
                {
                    "source": "engagement_event",
                    "id": ev.id,
                    "at": _iso(ev.occurred_at),
                    "summary": f"Engajamento: {ev.event_type}"
                    + (f" ({ev.channel})" if ev.channel else ""),
                    "refs": {
                        "event_type": ev.event_type,
                        "channel": ev.channel,
                        "source": getattr(ev, "source", None),
                        "intervention_log_id": getattr(ev, "intervention_log_id", None),
                    },
                }
            )
    except Exception:
        pass

    # Sort chronological (oldest first for timeline reading)
    def _sort_key(item: dict) -> str:
        return item.get("at") or ""

    items.sort(key=_sort_key)
    truncated = len(items) > limit
    if truncated:
        items = items[-limit:]

    return {
        "student_id": student_id,
        "tenant_id": auth.tenant_id,
        "count": len(items),
        "limit": limit,
        "truncated": truncated,
        "items": items,
        "definition": (
            "Linha do tempo somente com registros persistidos: "
            "risk_assessment, intervention_log, work_activity (+ events), engagement_event. "
            "Status de comunicação ≠ conclusão de atividade; absence of outcome ≠ evasão."
        ),
    }
