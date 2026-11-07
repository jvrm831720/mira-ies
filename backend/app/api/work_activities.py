"""Central de Trabalho: atividades operacionais atribuíveis (não InterventionLog)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import case, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthContext, require_min_role, require_permission
from app.db.session import get_db
from app.models.auth import User
from app.models.intervention import InterventionLog
from app.models.student import Student
from app.models.retention_campaign import RetentionCampaign
from app.models.work_activity import (
    WORK_ACTIVITY_TYPES,
    WORK_ORIGINS,
    WORK_PRIORITIES,
    WORK_STATUSES,
    WorkActivity,
    WorkActivityEvent,
)

router = APIRouter(prefix="/work", tags=["Central de Trabalho"])

_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "open": {"in_progress", "completed", "cancelled"},
    "in_progress": {"open", "completed", "cancelled"},
    "completed": set(),
    "cancelled": set(),
}

RESULT_KINDS = ("done", "unreachable", "deferred", "referred")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value else None


def _parse_uuid_param(value: Optional[str], field_name: str) -> Optional[str]:
    if value is None or value == "":
        return None
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(status_code=422, detail=f"{field_name} inválido (UUID esperado).")


def _serialize(activity: WorkActivity, assignee: Optional[User] = None) -> dict:
    overdue = bool(
        activity.due_at
        and activity.status in {"open", "in_progress"}
        and activity.due_at < _now()
    )
    return {
        "id": activity.id,
        "tenant_id": activity.tenant_id,
        "student_id": activity.student_id,
        "intervention_log_id": activity.intervention_log_id,
        "title": activity.title,
        "description": activity.description,
        "activity_type": activity.activity_type,
        "status": activity.status,
        "priority": activity.priority,
        "revision": activity.revision,
        "origin_type": activity.origin_type,
        "campaign_id": activity.campaign_id,
        "assignee_user_id": activity.assignee_user_id,
        "assignee": (
            {
                "id": assignee.id,
                "display_name": assignee.display_name,
                "email": assignee.email,
            }
            if assignee
            else None
        ),
        "created_by_user_id": activity.created_by_user_id,
        "due_at": _iso(activity.due_at),
        "completed_at": _iso(activity.completed_at),
        "cancelled_at": _iso(activity.cancelled_at),
        "created_at": _iso(activity.created_at),
        "updated_at": _iso(activity.updated_at),
        "overdue": overdue,
    }


def _serialize_event(event: WorkActivityEvent) -> dict:
    return {
        "id": event.id,
        "activity_id": event.activity_id,
        "actor_user_id": event.actor_user_id,
        "event_type": event.event_type,
        "payload": event.payload,
        "created_at": _iso(event.created_at),
    }


async def _load_assignees(db: AsyncSession, tenant_id: str, user_ids: set[str]) -> dict[str, User]:
    if not user_ids:
        return {}
    result = await db.execute(
        select(User).where(User.tenant_id == tenant_id, User.id.in_(list(user_ids)))
    )
    return {u.id: u for u in result.scalars().all()}


async def _require_tenant_member(
    db: AsyncSession, tenant_id: str, user_id: str
) -> User:
    result = await db.execute(
        select(User).where(
            User.id == user_id,
            User.tenant_id == tenant_id,
            User.is_active.is_(True),
        )
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=422,
            detail="Responsável inválido: usuário inativo ou de outra instituição.",
        )
    return user


async def _resolve_student_and_log(
    db: AsyncSession,
    *,
    tenant_id: str,
    student_id: Optional[str],
    intervention_log_id: Optional[str],
) -> tuple[Optional[str], Optional[str]]:
    """Validate tenant membership and consistency between student and intervention log."""
    resolved_student = student_id
    resolved_log = intervention_log_id
    log_row: Optional[InterventionLog] = None

    if intervention_log_id:
        result = await db.execute(
            select(InterventionLog).where(
                InterventionLog.id == intervention_log_id,
                InterventionLog.tenant_id == tenant_id,
            )
        )
        log_row = result.scalar_one_or_none()
        if not log_row:
            raise HTTPException(
                status_code=404, detail="Intervenção não encontrada neste tenant."
            )
        resolved_log = log_row.id

    if student_id:
        st = await db.execute(
            select(Student.id).where(
                Student.id == student_id, Student.tenant_id == tenant_id
            )
        )
        if not st.scalar_one_or_none():
            raise HTTPException(
                status_code=404, detail="Aluno não encontrado neste tenant."
            )
        resolved_student = student_id

    if resolved_student and log_row is not None:
        if log_row.student_id and log_row.student_id != resolved_student:
            raise HTTPException(
                status_code=422,
                detail="Aluno da atividade não corresponde ao aluno da intervenção vinculada.",
            )
    # If only log is set and log has student, optionally inherit — do NOT auto-write;
    # caller decides. Consistency only enforced when both present.

    return resolved_student, resolved_log


async def _append_event(
    db: AsyncSession,
    *,
    tenant_id: str,
    activity_id: str,
    actor_user_id: Optional[str],
    event_type: str,
    payload: Optional[dict] = None,
) -> None:
    db.add(
        WorkActivityEvent(
            tenant_id=tenant_id,
            activity_id=activity_id,
            actor_user_id=actor_user_id,
            event_type=event_type,
            payload=payload,
        )
    )


class CreateActivityBody(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=4000)
    activity_type: Literal["follow_up", "contact", "review", "other"] = "follow_up"
    student_id: Optional[str] = None
    intervention_log_id: Optional[str] = None
    assignee_user_id: Optional[str] = None
    due_at: Optional[datetime] = None
    priority: Literal["low", "normal", "high", "urgent"] = "normal"
    campaign_id: Optional[str] = None


class PatchActivityBody(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=4000)
    assignee_user_id: Optional[str] = None
    clear_assignee: bool = False
    due_at: Optional[datetime] = None
    clear_due: bool = False
    status: Optional[Literal["open", "in_progress", "completed", "cancelled"]] = None
    priority: Optional[Literal["low", "normal", "high", "urgent"]] = None
    student_id: Optional[str] = None
    clear_student: bool = False
    intervention_log_id: Optional[str] = None
    clear_intervention_log: bool = False


class ResultRecordedBody(BaseModel):
    note: str = Field(min_length=1, max_length=4000)
    kind: Optional[Literal["done", "unreachable", "deferred", "referred"]] = None


class CampaignActivityGenerationBody(BaseModel):
    campaign_id: str
    generation_key: str = Field(min_length=1, max_length=120)
    student_ids: list[str] = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=4000)
    activity_type: Literal["follow_up", "contact", "review", "other"] = "follow_up"
    priority: Literal["low", "normal", "high", "urgent"] = "normal"
    assignee_user_id: Optional[str] = None
    due_at: Optional[datetime] = None


@router.get("/activities")
async def list_activities(
    status_filter: Optional[str] = Query(None, alias="status"),
    assignee: Optional[str] = Query(
        None, description="user_id, 'me' ou 'unassigned'"
    ),
    origin_type: Optional[str] = Query(None, description="manual ou campaign"),
    priority: Optional[str] = Query(None, description="low, normal, high ou urgent"),
    student_id: Optional[str] = Query(None),
    intervention_log_id: Optional[str] = Query(None),
    overdue_only: bool = Query(False),
    limit: int = Query(100, ge=1, le=500),
    auth: AuthContext = Depends(require_min_role("operator")),
    db: AsyncSession = Depends(get_db),
):
    student_id = _parse_uuid_param(student_id, "student_id")
    intervention_log_id = _parse_uuid_param(intervention_log_id, "intervention_log_id")

    q = select(WorkActivity).where(WorkActivity.tenant_id == auth.tenant_id)
    if status_filter:
        if status_filter not in WORK_STATUSES:
            raise HTTPException(status_code=422, detail=f"status inválido: {status_filter}")
        q = q.where(WorkActivity.status == status_filter)
    if origin_type:
        if origin_type not in WORK_ORIGINS:
            raise HTTPException(status_code=422, detail=f"origin_type inválido: {origin_type}")
        q = q.where(WorkActivity.origin_type == origin_type)
    if priority:
        if priority not in WORK_PRIORITIES:
            raise HTTPException(status_code=422, detail=f"priority inválida: {priority}")
        q = q.where(WorkActivity.priority == priority)
    if assignee == "me":
        if not auth.user_id:
            return {"count": 0, "activities": []}
        q = q.where(WorkActivity.assignee_user_id == auth.user_id)
    elif assignee == "unassigned":
        q = q.where(WorkActivity.assignee_user_id.is_(None))
    elif assignee:
        q = q.where(WorkActivity.assignee_user_id == assignee)
    if student_id:
        q = q.where(WorkActivity.student_id == student_id)
    if intervention_log_id:
        q = q.where(WorkActivity.intervention_log_id == intervention_log_id)
    if overdue_only:
        q = q.where(
            WorkActivity.due_at.is_not(None),
            WorkActivity.due_at < _now(),
            WorkActivity.status.in_(["open", "in_progress"]),
        )
    priority_rank = case(
        (WorkActivity.priority == "urgent", 4),
        (WorkActivity.priority == "high", 3),
        (WorkActivity.priority == "normal", 2),
        else_=1,
    )
    q = q.order_by(
        priority_rank.desc(),
        WorkActivity.due_at.asc().nullslast(),
        WorkActivity.created_at.desc(),
    ).limit(limit)
    rows = (await db.execute(q)).scalars().all()
    assignees = await _load_assignees(
        db, auth.tenant_id, {r.assignee_user_id for r in rows if r.assignee_user_id}
    )
    return {
        "count": len(rows),
        "activities": [_serialize(r, assignees.get(r.assignee_user_id or "")) for r in rows],
    }


@router.get("/activities/mine")
async def list_my_activities(
    limit: int = Query(100, ge=1, le=500),
    auth: AuthContext = Depends(require_min_role("operator")),
    db: AsyncSession = Depends(get_db),
):
    """Atividades do usuário autenticado — user_id vem só do token, nunca do client."""
    if not auth.user_id:
        return {
            "count": 0,
            "activities": [],
            "note": "Sessão sem usuário (API key); fila pessoal vazia.",
        }
    q = (
        select(WorkActivity)
        .where(
            WorkActivity.tenant_id == auth.tenant_id,
            WorkActivity.assignee_user_id == auth.user_id,
            WorkActivity.status.in_(["open", "in_progress"]),
        )
        .order_by(WorkActivity.due_at.asc().nullslast(), WorkActivity.created_at.desc())
        .limit(limit)
    )
    rows = (await db.execute(q)).scalars().all()
    user = await db.get(User, auth.user_id)
    return {
        "count": len(rows),
        "activities": [
            _serialize(r, user if user and user.tenant_id == auth.tenant_id else None)
            for r in rows
        ],
    }


@router.get("/activities/summary")
async def work_activity_summary(
    auth: AuthContext = Depends(require_min_role("operator")),
    db: AsyncSession = Depends(get_db),
):
    """Contadores sem limite de listagem para enxergar backlog e gargalos reais."""
    now = _now()
    active = WorkActivity.status.in_(["open", "in_progress"])
    row = (
        await db.execute(
            select(
                func.count(case((active, WorkActivity.id))).label("pending"),
                func.count(
                    case(
                        (
                            active
                            & WorkActivity.due_at.is_not(None)
                            & (WorkActivity.due_at < now),
                            WorkActivity.id,
                        )
                    )
                ).label("overdue"),
                func.count(
                    case(
                        (
                            (WorkActivity.status == "completed")
                            & (WorkActivity.completed_at >= now - timedelta(days=7)),
                            WorkActivity.id,
                        )
                    )
                ).label("completed_7d"),
                func.count(
                    case((active & WorkActivity.assignee_user_id.is_(None), WorkActivity.id))
                ).label("unassigned"),
                func.count(
                    case(
                        (active & (WorkActivity.origin_type == "campaign"), WorkActivity.id)
                    )
                ).label("campaign_pending"),
                func.count(
                    case((active & (WorkActivity.priority == "urgent"), WorkActivity.id))
                ).label("urgent_pending"),
            ).where(WorkActivity.tenant_id == auth.tenant_id)
        )
    ).one()
    return {
        "pending": int(row.pending or 0),
        "overdue": int(row.overdue or 0),
        "completed_7d": int(row.completed_7d or 0),
        "unassigned": int(row.unassigned or 0),
        "campaign_pending": int(row.campaign_pending or 0),
        "urgent_pending": int(row.urgent_pending or 0),
        "as_of": _iso(now),
    }



@router.get("/activities/priority-no-contact")
async def critical_students_without_recent_contact(
    auth: AuthContext = Depends(require_permission("students.sensitive.view")),
    db: AsyncSession = Depends(get_db),
):
    """Verified tenant-wide counts; no capped work queue, no assumed contact for missing data.

    A confirmed contact is a sent intervention or an explicit human\n    result_recorded(kind=done) event. Sending/unknown interventions and in-progress human
    contacts are held for review, not mistaken for safe outreach candidates.
    """
    now = _now()
    cutoff = now - timedelta(days=7)
    critical = (
        Student.tenant_id == auth.tenant_id,
        Student.is_active.is_(True),
        Student.risk_level == "critico",
        Student.risk_score.is_not(None),
    )
    sent = exists(
        select(InterventionLog.id).where(
            InterventionLog.tenant_id == auth.tenant_id,
            InterventionLog.student_id == Student.id,
            InterventionLog.status == "sent",
            InterventionLog.created_at >= cutoff,
        )
    )
    human_done = exists(
        select(WorkActivityEvent.id)
        .join(WorkActivity, WorkActivityEvent.activity_id == WorkActivity.id)
        .where(
            WorkActivity.tenant_id == auth.tenant_id,
            WorkActivity.student_id == Student.id,
            WorkActivity.activity_type == "contact",
            WorkActivityEvent.tenant_id == auth.tenant_id,
            WorkActivityEvent.event_type == "result_recorded",
            WorkActivityEvent.payload["kind"].astext == "done",
            WorkActivityEvent.created_at >= cutoff,
        )
    )
    uncertain_sent = exists(
        select(InterventionLog.id).where(
            InterventionLog.tenant_id == auth.tenant_id,
            InterventionLog.student_id == Student.id,
            InterventionLog.status.in_(("sending", "unknown")),
            InterventionLog.created_at >= cutoff,
        )
    )
    human_in_progress = exists(
        select(WorkActivity.id).where(
            WorkActivity.tenant_id == auth.tenant_id,
            WorkActivity.student_id == Student.id,
            WorkActivity.activity_type == "contact",
            (
                (WorkActivity.status == "in_progress")
                | (
                    (WorkActivity.status == "completed")
                    & (WorkActivity.completed_at >= cutoff)
                )
            ),
        )
    )
    confirmed = sent | human_done
    uncertain = ~confirmed & (uncertain_sent | human_in_progress)
    actionable = ~confirmed & ~uncertain
    aggregates = (await db.execute(
        select(
            func.count(Student.id).label("critical_total"),
            func.count(case((confirmed, Student.id))).label("contacted_7d"),
            func.count(case((uncertain, Student.id))).label("pending_verification"),
            func.count(case((actionable, Student.id))).label("without_contact_7d"),
        ).where(*critical)
    )).one()
    top = (await db.execute(
        select(Student.id, Student.nome, Student.matricula, Student.risk_score)
        .where(*critical, actionable)
        .order_by(Student.risk_score.desc(), Student.id)
        .limit(8)
    )).all()
    return {
        "as_of": _iso(now),
        "window_days": 7,
        "critical_total": int(aggregates.critical_total or 0),
        "contacted_7d": int(aggregates.contacted_7d or 0),
        "pending_verification": int(aggregates.pending_verification or 0),
        "without_contact_7d": int(aggregates.without_contact_7d or 0),
        "candidates": [
            {"id": row.id, "nome": row.nome, "matricula": row.matricula,
             "risk_score": row.risk_score}
            for row in top
        ],
        "count_scope": "all active tenant students scored as critical",
        "policy": "Sent interventions and explicitly successful human result events count as contact. "
                  "Sending/unknown interventions and pending/unverified human contacts are excluded "
                  "from the candidate count until verified.",
    }


@router.post("/activities", status_code=201)
async def create_activity(
    body: CreateActivityBody,
    auth: AuthContext = Depends(require_min_role("operator")),
    db: AsyncSession = Depends(get_db),
):
    if body.activity_type not in WORK_ACTIVITY_TYPES:
        raise HTTPException(status_code=422, detail="activity_type inválido")
    title = body.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="title não pode ser vazio.")

    student_id = _parse_uuid_param(body.student_id, "student_id") if body.student_id else None
    intervention_log_id = (
        _parse_uuid_param(body.intervention_log_id, "intervention_log_id")
        if body.intervention_log_id
        else None
    )
    student_id, intervention_log_id = await _resolve_student_and_log(
        db,
        tenant_id=auth.tenant_id,
        student_id=student_id,
        intervention_log_id=intervention_log_id,
    )

    campaign_id = _parse_uuid_param(body.campaign_id, "campaign_id") if body.campaign_id else None
    log_campaign_id = None
    if intervention_log_id:
        log_campaign_id = (
            await db.execute(
                select(InterventionLog.campaign_id).where(
                    InterventionLog.id == intervention_log_id,
                    InterventionLog.tenant_id == auth.tenant_id,
                )
            )
        ).scalar_one_or_none()
        if campaign_id and log_campaign_id and str(campaign_id) != str(log_campaign_id):
            raise HTTPException(
                status_code=422,
                detail="A campanha informada não corresponde à campanha da intervenção vinculada.",
            )
        if not campaign_id and log_campaign_id:
            try:
                possible_campaign_id = str(UUID(str(log_campaign_id)))
            except (ValueError, TypeError, AttributeError):
                possible_campaign_id = None
            if possible_campaign_id:
                campaign_exists = await db.execute(
                    select(RetentionCampaign.id).where(
                        RetentionCampaign.id == possible_campaign_id,
                        RetentionCampaign.tenant_id == auth.tenant_id,
                    )
                )
                if campaign_exists.scalar_one_or_none():
                    campaign_id = possible_campaign_id

    if campaign_id:
        campaign_exists = await db.execute(
            select(RetentionCampaign.id).where(
                RetentionCampaign.id == campaign_id,
                RetentionCampaign.tenant_id == auth.tenant_id,
            )
        )
        if not campaign_exists.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Campanha não encontrada neste tenant.")

    assignee = None
    if body.assignee_user_id:
        assignee = await _require_tenant_member(db, auth.tenant_id, body.assignee_user_id)

    activity = WorkActivity(
        tenant_id=auth.tenant_id,
        student_id=student_id,
        intervention_log_id=intervention_log_id,
        title=title,
        description=(body.description or "").strip() or None,
        activity_type=body.activity_type,
        status="open",
        priority=body.priority,
        origin_type="campaign" if campaign_id else "manual",
        campaign_id=campaign_id,
        assignee_user_id=assignee.id if assignee else None,
        created_by_user_id=auth.user_id,
        due_at=body.due_at,
    )
    db.add(activity)
    await db.flush()
    await _append_event(
        db,
        tenant_id=auth.tenant_id,
        activity_id=activity.id,
        actor_user_id=auth.user_id,
        event_type="created",
        payload={
            "title": activity.title,
            "priority": activity.priority,
            "origin_type": activity.origin_type,
            "campaign_id": activity.campaign_id,
            "assignee_user_id": activity.assignee_user_id,
            "due_at": _iso(activity.due_at),
            "student_id": activity.student_id,
            "intervention_log_id": activity.intervention_log_id,
        },
    )
    await db.commit()
    await db.refresh(activity)
    return _serialize(activity, assignee)


@router.post("/activities/campaign-generated")
async def generate_campaign_activities(
    body: CampaignActivityGenerationBody,
    auth: AuthContext = Depends(require_min_role("operator")),
    db: AsyncSession = Depends(get_db),
):
    """Cria tarefas humanas para uma audiência explícita, idempotente por campanha/aluno.

    Campanhas só devem chamar esta operação quando uma regra exigir ação humana. Uma
    simulação ou dry-run de comunicação, por si só, não gera tarefas operacionais.
    """
    campaign_id = _parse_uuid_param(body.campaign_id, "campaign_id")
    campaign = await db.execute(
        select(RetentionCampaign).where(
            RetentionCampaign.id == campaign_id,
            RetentionCampaign.tenant_id == auth.tenant_id,
        ).with_for_update()
    )
    if not campaign.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Campanha não encontrada neste tenant.")

    generation_key = body.generation_key.strip()
    if not generation_key:
        raise HTTPException(status_code=422, detail="generation_key não pode ser vazio.")
    title = body.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="title não pode ser vazio.")
    student_ids = list(dict.fromkeys(_parse_uuid_param(value, "student_ids") for value in body.student_ids))
    students = await db.execute(
        select(Student.id).where(
            Student.tenant_id == auth.tenant_id,
            Student.id.in_(student_ids),
        )
    )
    valid_student_ids = set(students.scalars().all())
    if valid_student_ids != set(student_ids):
        raise HTTPException(status_code=404, detail="Um ou mais alunos não foram encontrados neste tenant.")

    assignee = None
    if body.assignee_user_id:
        assignee = await _require_tenant_member(db, auth.tenant_id, body.assignee_user_id)

    source_keys = {
        student_id: f"campaign:{campaign_id}:g:{generation_key}:{student_id}"
        for student_id in student_ids
    }
    existing_result = await db.execute(
        select(WorkActivity).where(
            WorkActivity.tenant_id == auth.tenant_id,
            WorkActivity.source_key.in_(list(source_keys.values())),
        )
    )
    existing_rows = list(existing_result.scalars().all())
    existing_keys = {row.source_key for row in existing_rows}
    created_rows: list[WorkActivity] = []
    for student_id in student_ids:
        source_key = source_keys[student_id]
        if source_key in existing_keys:
            continue
        activity = WorkActivity(
            tenant_id=auth.tenant_id,
            student_id=student_id,
            title=title,
            description=(body.description or "").strip() or None,
            activity_type=body.activity_type,
            status="open",
            priority=body.priority,
            origin_type="campaign",
            campaign_id=campaign_id,
            source_key=source_key,
            assignee_user_id=assignee.id if assignee else None,
            created_by_user_id=auth.user_id,
            due_at=body.due_at,
        )
        db.add(activity)
        await db.flush()
        await _append_event(
            db,
            tenant_id=auth.tenant_id,
            activity_id=activity.id,
            actor_user_id=auth.user_id,
            event_type="created",
            payload={
                "title": activity.title,
                "origin_type": "campaign",
                "campaign_id": campaign_id,
                "generation_key": generation_key,
                "student_id": student_id,
                "priority": activity.priority,
                "assignee_user_id": activity.assignee_user_id,
                "due_at": _iso(activity.due_at),
            },
        )
        created_rows.append(activity)

    await db.commit()
    rows = existing_rows + created_rows
    assignees = await _load_assignees(
        db, auth.tenant_id, {row.assignee_user_id for row in rows if row.assignee_user_id}
    )
    return {
        "campaign_id": campaign_id,
        "generation_key": generation_key,
        "count": len(rows),
        "created_count": len(created_rows),
        "reused_count": len(existing_rows),
        "activities": [_serialize(row, assignees.get(row.assignee_user_id or "")) for row in rows],
    }


@router.get("/activities/{activity_id}")
async def get_activity(
    activity_id: str,
    auth: AuthContext = Depends(require_min_role("operator")),
    db: AsyncSession = Depends(get_db),
):
    activity_id = _parse_uuid_param(activity_id, "activity_id")
    activity = await db.get(WorkActivity, activity_id)
    if not activity or activity.tenant_id != auth.tenant_id:
        raise HTTPException(status_code=404, detail="Atividade não encontrada.")
    assignee = None
    if activity.assignee_user_id:
        assignee = await db.get(User, activity.assignee_user_id)
        if assignee and assignee.tenant_id != auth.tenant_id:
            assignee = None
    return _serialize(activity, assignee)


@router.patch("/activities/{activity_id}")
async def patch_activity(
    activity_id: str,
    body: PatchActivityBody,
    auth: AuthContext = Depends(require_min_role("operator")),
    db: AsyncSession = Depends(get_db),
):
    activity_id = _parse_uuid_param(activity_id, "activity_id")
    activity = (await db.execute(select(WorkActivity).where(
        WorkActivity.id == activity_id, WorkActivity.tenant_id == auth.tenant_id
    ).with_for_update())).scalar_one_or_none()
    if activity is None:
        raise HTTPException(status_code=404, detail="Atividade não encontrada.")

    relation_touch = (
        body.student_id is not None
        or body.clear_student
        or body.intervention_log_id is not None
        or body.clear_intervention_log
    )

    if activity.status in {"completed", "cancelled"} and (
        body.status is None or body.status == activity.status
    ):
        if (
            body.title
            or body.description is not None
            or body.assignee_user_id
            or body.clear_assignee
            or body.due_at
            or body.clear_due
            or body.priority is not None
            or relation_touch
        ):
            raise HTTPException(
                status_code=422,
                detail="Atividade concluída ou cancelada não pode ser editada.",
            )

    changed_fields: list[str] = []
    if body.title is not None:
        next_title = body.title.strip()
        if not next_title:
            raise HTTPException(status_code=422, detail="title não pode ser vazio.")
        if next_title != activity.title:
            activity.title = next_title
            changed_fields.append("title")

    if body.description is not None:
        next_description = body.description.strip() or None
        if next_description != activity.description:
            activity.description = next_description
            changed_fields.append("description")

    if changed_fields:
        await _append_event(
            db,
            tenant_id=auth.tenant_id,
            activity_id=activity.id,
            actor_user_id=auth.user_id,
            event_type="details_changed",
            payload={"fields": changed_fields},
        )

    if body.priority is not None and body.priority != activity.priority:
        previous_priority = activity.priority
        activity.priority = body.priority
        await _append_event(
            db,
            tenant_id=auth.tenant_id,
            activity_id=activity.id,
            actor_user_id=auth.user_id,
            event_type="priority_changed",
            payload={"from": previous_priority, "to": body.priority},
        )

    # Relation updates
    next_student = activity.student_id
    next_log = activity.intervention_log_id
    if body.clear_student:
        next_student = None
    elif body.student_id is not None:
        next_student = _parse_uuid_param(body.student_id, "student_id")
    if body.clear_intervention_log:
        next_log = None
    elif body.intervention_log_id is not None:
        next_log = _parse_uuid_param(body.intervention_log_id, "intervention_log_id")

    if relation_touch:
        next_student, next_log = await _resolve_student_and_log(
            db,
            tenant_id=auth.tenant_id,
            student_id=next_student,
            intervention_log_id=next_log,
        )
        if activity.source_key and next_student != activity.student_id:
            raise HTTPException(
                status_code=422,
                detail="O aluno de uma atividade gerada por campanha não pode ser alterado.",
            )
        if next_student != activity.student_id or next_log != activity.intervention_log_id:
            prev_s, prev_l = activity.student_id, activity.intervention_log_id
            activity.student_id = next_student
            activity.intervention_log_id = next_log
            await _append_event(
                db,
                tenant_id=auth.tenant_id,
                activity_id=activity.id,
                actor_user_id=auth.user_id,
                event_type="relations_changed",
                payload={
                    "student_id": {"from": prev_s, "to": next_student},
                    "intervention_log_id": {"from": prev_l, "to": next_log},
                },
            )

    if body.clear_assignee:
        prev = activity.assignee_user_id
        if prev is not None:
            activity.assignee_user_id = None
            await _append_event(
                db,
                tenant_id=auth.tenant_id,
                activity_id=activity.id,
                actor_user_id=auth.user_id,
                event_type="assignee_changed",
                payload={"from": prev, "to": None},
            )
    elif body.assignee_user_id is not None:
        member = await _require_tenant_member(db, auth.tenant_id, body.assignee_user_id)
        prev = activity.assignee_user_id
        if prev != member.id:
            activity.assignee_user_id = member.id
            await _append_event(
                db,
                tenant_id=auth.tenant_id,
                activity_id=activity.id,
                actor_user_id=auth.user_id,
                event_type="assignee_changed",
                payload={"from": prev, "to": member.id},
            )

    if body.clear_due:
        prev = _iso(activity.due_at)
        if prev is not None:
            activity.due_at = None
            await _append_event(
                db,
                tenant_id=auth.tenant_id,
                activity_id=activity.id,
                actor_user_id=auth.user_id,
                event_type="due_changed",
                payload={"from": prev, "to": None},
            )
    elif body.due_at is not None:
        prev = _iso(activity.due_at)
        if prev != _iso(body.due_at):
            activity.due_at = body.due_at
            await _append_event(
                db,
                tenant_id=auth.tenant_id,
                activity_id=activity.id,
                actor_user_id=auth.user_id,
                event_type="due_changed",
                payload={"from": prev, "to": _iso(body.due_at)},
            )

    if body.status is not None and body.status != activity.status:
        allowed = _ALLOWED_TRANSITIONS.get(activity.status, set())
        if body.status not in allowed:
            raise HTTPException(
                status_code=422,
                detail=f"Transição inválida: {activity.status} → {body.status}",
            )
        prev = activity.status
        activity.status = body.status
        if body.status == "completed":
            activity.completed_at = _now()
            event_type = "completed"
        elif body.status == "cancelled":
            activity.cancelled_at = _now()
            event_type = "cancelled"
        else:
            event_type = "status_changed"
        await _append_event(
            db,
            tenant_id=auth.tenant_id,
            activity_id=activity.id,
            actor_user_id=auth.user_id,
            event_type=event_type,
            payload={"from": prev, "to": body.status},
        )

    activity.revision += 1
    activity.updated_at = _now()
    await db.commit()
    await db.refresh(activity)
    assignee = None
    if activity.assignee_user_id:
        assignee = await db.get(User, activity.assignee_user_id)
        if assignee and assignee.tenant_id != auth.tenant_id:
            assignee = None
    return _serialize(activity, assignee)


@router.post("/activities/{activity_id}/result")
async def record_activity_result(
    activity_id: str,
    body: ResultRecordedBody,
    auth: AuthContext = Depends(require_min_role("operator")),
    db: AsyncSession = Depends(get_db),
):
    """Registra resultado operacional via WorkActivityEvent (não altera status nem InterventionLog.outcome)."""
    activity_id = _parse_uuid_param(activity_id, "activity_id")
    activity = (await db.execute(select(WorkActivity).where(
        WorkActivity.id == activity_id, WorkActivity.tenant_id == auth.tenant_id
    ).with_for_update())).scalar_one_or_none()
    if not activity or activity.tenant_id != auth.tenant_id:
        raise HTTPException(status_code=404, detail="Atividade não encontrada.")

    note = body.note.strip()
    if not note:
        raise HTTPException(status_code=422, detail="note é obrigatório.")
    if body.kind is not None and body.kind not in RESULT_KINDS:
        raise HTTPException(status_code=422, detail=f"kind inválido: {body.kind}")

    payload: dict = {"note": note}
    if body.kind:
        payload["kind"] = body.kind

    await _append_event(
        db,
        tenant_id=auth.tenant_id,
        activity_id=activity.id,
        actor_user_id=auth.user_id,
        event_type="result_recorded",
        payload=payload,
    )
    activity.revision += 1
    activity.updated_at = _now()
    await db.commit()

    events = (
        await db.execute(
            select(WorkActivityEvent)
            .where(
                WorkActivityEvent.tenant_id == auth.tenant_id,
                WorkActivityEvent.activity_id == activity_id,
            )
            .order_by(WorkActivityEvent.created_at.asc())
        )
    ).scalars().all()
    return {
        "activity_id": activity.id,
        "status": activity.status,
        "intervention_log_id": activity.intervention_log_id,
        "event_type": "result_recorded",
        "count": len(events),
        "events": [_serialize_event(e) for e in events],
        "note": "result_recorded não altera status da atividade nem outcome da intervenção.",
    }


@router.get("/activities/{activity_id}/events")
async def list_activity_events(
    activity_id: str,
    auth: AuthContext = Depends(require_min_role("operator")),
    db: AsyncSession = Depends(get_db),
):
    activity_id = _parse_uuid_param(activity_id, "activity_id")
    activity = await db.get(WorkActivity, activity_id)
    if not activity or activity.tenant_id != auth.tenant_id:
        raise HTTPException(status_code=404, detail="Atividade não encontrada.")
    result = await db.execute(
        select(WorkActivityEvent)
        .where(
            WorkActivityEvent.tenant_id == auth.tenant_id,
            WorkActivityEvent.activity_id == activity_id,
        )
        .order_by(WorkActivityEvent.created_at.asc())
    )
    events = result.scalars().all()
    return {"count": len(events), "events": [_serialize_event(e) for e in events]}
