"""Central de Trabalho: atividades operacionais atribuíveis (não InterventionLog)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthContext, require_min_role
from app.db.session import get_db
from app.models.auth import User
from app.models.intervention import InterventionLog
from app.models.student import Student
from app.models.work_activity import (
    WORK_ACTIVITY_TYPES,
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


class PatchActivityBody(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=4000)
    assignee_user_id: Optional[str] = None
    clear_assignee: bool = False
    due_at: Optional[datetime] = None
    clear_due: bool = False
    status: Optional[Literal["open", "in_progress", "completed", "cancelled"]] = None
    student_id: Optional[str] = None
    clear_student: bool = False
    intervention_log_id: Optional[str] = None
    clear_intervention_log: bool = False


class ResultRecordedBody(BaseModel):
    note: str = Field(min_length=1, max_length=4000)
    kind: Optional[Literal["done", "unreachable", "deferred", "referred"]] = None


@router.get("/activities")
async def list_activities(
    status_filter: Optional[str] = Query(None, alias="status"),
    assignee: Optional[str] = Query(
        None, description="user_id, 'me' ou 'unassigned'"
    ),
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
    q = q.order_by(WorkActivity.due_at.asc().nullslast(), WorkActivity.created_at.desc()).limit(limit)
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


@router.post("/activities", status_code=201)
async def create_activity(
    body: CreateActivityBody,
    auth: AuthContext = Depends(require_min_role("operator")),
    db: AsyncSession = Depends(get_db),
):
    if body.activity_type not in WORK_ACTIVITY_TYPES:
        raise HTTPException(status_code=422, detail="activity_type inválido")

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

    assignee = None
    if body.assignee_user_id:
        assignee = await _require_tenant_member(db, auth.tenant_id, body.assignee_user_id)

    activity = WorkActivity(
        tenant_id=auth.tenant_id,
        student_id=student_id,
        intervention_log_id=intervention_log_id,
        title=body.title.strip(),
        description=(body.description or "").strip() or None,
        activity_type=body.activity_type,
        status="open",
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
            "assignee_user_id": activity.assignee_user_id,
            "due_at": _iso(activity.due_at),
            "student_id": activity.student_id,
            "intervention_log_id": activity.intervention_log_id,
        },
    )
    await db.commit()
    await db.refresh(activity)
    return _serialize(activity, assignee)


@router.get("/activities/{activity_id}")
async def get_activity(
    activity_id: str,
    auth: AuthContext = Depends(require_min_role("operator")),
    db: AsyncSession = Depends(get_db),
):
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
    activity = await db.get(WorkActivity, activity_id)
    if not activity or activity.tenant_id != auth.tenant_id:
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
            or relation_touch
        ):
            raise HTTPException(
                status_code=422,
                detail="Atividade concluída ou cancelada não pode ser editada.",
            )

    if body.title is not None:
        activity.title = body.title.strip()

    if body.description is not None:
        activity.description = body.description.strip() or None

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
    activity = await db.get(WorkActivity, activity_id)
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
