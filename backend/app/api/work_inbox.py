"""Wave 5: paginated human Work Inbox, deterministic priority and atomic resolution.

This API never sends a message, settles an invoice or changes InterventionLog.
Existing WorkActivity and append-only WorkActivityEvent are the single source
of truth. Every mutation checks tenant, human assignment, revision and idempotency.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthContext, require_min_role
from app.db.session import get_db
from app.models.auth import User
from app.models.work_activity import WorkActivity, WorkActivityEvent

router = APIRouter(prefix="/work", tags=["Meu Trabalho / Work Inbox"])
Perspective = Literal["mine", "team", "unassigned", "history"]
Outcome = Literal["done", "unreachable", "deferred", "referred"]


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _human(auth: AuthContext) -> str:
    if not auth.user_id or not auth.session_id:
        raise HTTPException(status_code=403, detail="Meu Trabalho exige uma sessão humana ativa.")
    return auth.user_id


def _uuid(raw: str) -> str:
    try:
        return str(UUID(raw))
    except (ValueError, TypeError, AttributeError) as exc:
        raise HTTPException(status_code=404, detail="Atividade não encontrada.") from exc


def priority_reasons(item: WorkActivity, at: datetime) -> list[dict[str, str]]:
    """Only documented stored signals: never infer student risk, payment or delivery."""
    reasons: list[dict[str, str]] = []
    for level, label in (("urgent", "Prioridade urgente definida"), ("high", "Prioridade alta definida")):
        if item.priority == level:
            reasons.append({"code": "manual_priority", "label": label})
            break
    if item.status in ("open", "in_progress") and item.due_at:
        due = item.due_at
        if due.tzinfo is None:
            due = due.replace(tzinfo=timezone.utc)
        if due < at:
            reasons.append({"code": "overdue", "label": "Prazo da atividade vencido"})
        elif due <= at + timedelta(hours=24):
            reasons.append({"code": "due_soon", "label": "Vence nas próximas 24 horas"})
    if item.assignee_user_id is None:
        reasons.append({"code": "unassigned", "label": "Nenhum responsável atribuído"})
    if item.origin_type == "campaign":
        reasons.append({"code": "campaign_source", "label": "Atividade gerada a partir de campanha"})
    if not reasons:
        reasons.append({"code": "scheduled", "label": "Ordem definida por prioridade e prazo registrados"})
    return reasons


def _task(item: WorkActivity, at: datetime, assignee: User | None = None) -> dict:
    from app.api.work_activities import _serialize
    payload = _serialize(item, assignee)
    payload["priority_reasons"] = priority_reasons(item, at)
    payload["result_semantics"] = "human_work_only"
    return payload


def _active():
    return WorkActivity.status.in_(("open", "in_progress"))


def _perspective_query(tenant_id: str, user_id: str, perspective: Perspective):
    q = select(WorkActivity).where(WorkActivity.tenant_id == tenant_id)
    if perspective == "mine":
        return q.where(_active(), WorkActivity.assignee_user_id == user_id)
    if perspective == "team":
        return q.where(_active(), WorkActivity.assignee_user_id.is_not(None),
                       WorkActivity.assignee_user_id != user_id)
    if perspective == "unassigned":
        return q.where(_active(), WorkActivity.assignee_user_id.is_(None))
    return q.where(WorkActivity.status.in_(("completed", "cancelled")))


def _priority_order(at: datetime):
    manual = case(
        (WorkActivity.priority == "urgent", 4),
        (WorkActivity.priority == "high", 3),
        (WorkActivity.priority == "normal", 2),
        else_=1,
    )
    overdue = case(
        (WorkActivity.due_at.is_not(None) & (WorkActivity.due_at < at), 500),
        (WorkActivity.due_at.is_not(None)
         & (WorkActivity.due_at <= at + timedelta(hours=24)), 250),
        else_=0,
    )
    return manual * 1000 + overdue


class ResolveBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
    operation_key: str = Field(min_length=8, max_length=80, pattern=r"^[A-Za-z0-9_-]{8,80}$")
    kind: Outcome
    note: str = Field(min_length=1, max_length=4000)
    next_due_at: datetime | None = None

    @model_validator(mode="after")
    def check_defer(self):
        if not self.note.strip():
            raise ValueError("Resultado exige observação.")
        if self.kind == "deferred" and self.next_due_at is None:
            raise ValueError("Adiar exige nova data de vencimento.")
        if self.kind != "deferred" and self.next_due_at is not None:
            raise ValueError("Nova data somente para resultado adiado.")
        if self.next_due_at is not None and (
            self.next_due_at.tzinfo is None or self.next_due_at <= now_utc()
        ):
            raise ValueError("O novo prazo deve estar no futuro e conter timezone.")
        return self


class ClaimBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
    operation_key: str = Field(min_length=8, max_length=80, pattern=r"^[A-Za-z0-9_-]{8,80}$")


async def _locked(db: AsyncSession, tenant_id: str, activity_id: str) -> WorkActivity:
    row = (await db.execute(
        select(WorkActivity).where(
            WorkActivity.tenant_id == tenant_id, WorkActivity.id == _uuid(activity_id)
        ).with_for_update()
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Atividade não encontrada.")
    return row


async def _existing(
    db: AsyncSession, tenant: str, activity: str, key: str,
) -> WorkActivityEvent | None:
    return (await db.execute(select(WorkActivityEvent).where(
        WorkActivityEvent.tenant_id == tenant,
        WorkActivityEvent.activity_id == activity,
        WorkActivityEvent.operation_key == key,
    ))).scalar_one_or_none()


def _guard_revision(activity: WorkActivity, expected: int) -> None:
    if activity.revision != expected:
        raise HTTPException(status_code=409, detail={
            "code": "WORK_REVISION_CONFLICT",
            "current_revision": activity.revision,
            "message": "Atividade alterada em outra sessão. Atualize a fila antes de decidir.",
        })


async def _assignee(db: AsyncSession, tenant: str, user_id: str | None) -> User | None:
    if not user_id:
        return None
    return (await db.execute(select(User).where(
        User.tenant_id == tenant, User.id == user_id,
    ))).scalar_one_or_none()


@router.get("/inbox")
async def work_inbox(
    view: Perspective = "mine",
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0, le=1000000),
    auth: AuthContext = Depends(require_min_role("operator")),
    db: AsyncSession = Depends(get_db),
):
    user_id = _human(auth)
    at = now_utc()
    query = _perspective_query(auth.tenant_id, user_id, view)
    criteria = tuple(query.whereclause.clauses) if hasattr(query.whereclause, "clauses") else (query.whereclause,)
    count = (await db.execute(select(func.count(WorkActivity.id)).where(*criteria))).scalar_one()
    if view == "history":
        query = query.order_by(WorkActivity.updated_at.desc(), WorkActivity.id.desc())
    else:
        query = query.order_by(_priority_order(at).desc(),
                               WorkActivity.due_at.asc().nullslast(),
                               WorkActivity.created_at.asc(), WorkActivity.id.asc())
    items = (await db.execute(query.offset(offset).limit(limit))).scalars().all()
    ids = {item.assignee_user_id for item in items if item.assignee_user_id}
    members = (await db.execute(select(User).where(
        User.tenant_id == auth.tenant_id, User.id.in_(list(ids))
    ))).scalars().all() if ids else []
    mapped = {member.id: member for member in members}
    return {
        "view": view, "as_of": at.isoformat(), "total": count,
        "limit": limit, "offset": offset,
        "has_more": offset + len(items) < count,
        "next_offset": offset + len(items) if offset + len(items) < count else None,
        "items": [_task(item, at, mapped.get(item.assignee_user_id)) for item in items],
        "total_scope": "filtered_workspace_perspective",
    }


@router.get("/inbox/counts")
async def work_inbox_counts(
    auth: AuthContext = Depends(require_min_role("operator")),
    db: AsyncSession = Depends(get_db),
):
    user = _human(auth)
    data: dict[str, int] = {}
    for view in ("mine", "team", "unassigned", "history"):
        query = _perspective_query(auth.tenant_id, user, view)
        where = query.whereclause
        data[view] = int((await db.execute(select(func.count(WorkActivity.id)).where(where))).scalar_one())
    return {"counts": data, "scope": "full_tenant_with_user_perspective", "as_of": now_utc().isoformat()}


@router.post("/activities/{activity_id}/claim")
async def claim_work_activity(
    activity_id: str,
    body: ClaimBody,
    auth: AuthContext = Depends(require_min_role("operator")),
    db: AsyncSession = Depends(get_db),
):
    user_id = _human(auth)
    item = await _locked(db, auth.tenant_id, activity_id)
    prior = await _existing(db, auth.tenant_id, item.id, body.operation_key)
    if prior:
        if prior.event_type != "claimed" or prior.actor_user_id != user_id:
            raise HTTPException(status_code=409, detail="Chave de operação já utilizada.")
        return {"activity": _task(item, now_utc(), await _assignee(db, auth.tenant_id, item.assignee_user_id)),
                "idempotent_replay": True, "event_id": prior.id}
    _guard_revision(item, body.expected_revision)
    if item.status not in ("open", "in_progress") or item.assignee_user_id not in (None, user_id):
        raise HTTPException(status_code=409, detail="Atividade indisponível para atribuição.")
    previous = item.assignee_user_id
    item.assignee_user_id = user_id
    item.revision += 1
    item.updated_at = now_utc()
    event = WorkActivityEvent(
        tenant_id=auth.tenant_id, activity_id=item.id, actor_user_id=user_id,
        event_type="claimed", operation_key=body.operation_key,
        payload={"from": previous, "to": user_id, "domain": "human_work"},
    )
    db.add(event)
    assignee = await _assignee(db, auth.tenant_id, user_id)
    await db.commit()
    return {"activity": _task(item, now_utc(), assignee),
            "idempotent_replay": False, "event_id": event.id}


@router.post("/activities/{activity_id}/resolve")
async def resolve_work_activity(
    activity_id: str,
    body: ResolveBody,
    auth: AuthContext = Depends(require_min_role("operator")),
    db: AsyncSession = Depends(get_db),
):
    user_id = _human(auth)
    item = await _locked(db, auth.tenant_id, activity_id)
    prior = await _existing(db, auth.tenant_id, item.id, body.operation_key)
    payload = {"kind": body.kind, "note": body.note.strip(),
               "next_due_at": body.next_due_at.isoformat() if body.next_due_at else None,
               "domain": "human_work"}
    if prior:
        previous = prior.payload or {}
        if (prior.event_type != "human_result_resolved" or prior.actor_user_id != user_id or
            any(previous.get(key) != value for key, value in payload.items())):
            raise HTTPException(status_code=409, detail="Chave idempotente associada a outro resultado.")
        return {"activity": _task(item, now_utc(), await _assignee(db, auth.tenant_id, item.assignee_user_id)),
                "event_id": prior.id, "idempotent_replay": True}
    _guard_revision(item, body.expected_revision)
    if item.assignee_user_id != user_id:
        raise HTTPException(status_code=403, detail="Atribua esta atividade a você antes de resolver.")
    if item.status not in ("open", "in_progress"):
        raise HTTPException(status_code=409, detail="Atividade já encerrada.")
    previous = item.status
    if body.kind == "deferred":
        item.due_at = body.next_due_at
        item.status = "open"
    else:
        item.status = "completed"
        item.completed_at = now_utc()
    item.revision += 1
    item.updated_at = now_utc()
    event = WorkActivityEvent(
        tenant_id=auth.tenant_id, activity_id=item.id, actor_user_id=user_id,
        event_type="human_result_resolved", operation_key=body.operation_key,
        payload={**payload, "from_status": previous, "to_status": item.status},
    )
    db.add(event)
    assignee = await _assignee(db, auth.tenant_id, item.assignee_user_id)
    await db.commit()
    return {"activity": _task(item, now_utc(), assignee),
            "event_id": event.id, "idempotent_replay": False}
