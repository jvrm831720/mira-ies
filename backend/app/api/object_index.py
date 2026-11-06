"""Safe, server-filtered Object Index for students.

The legacy GET /students contract is intentionally unchanged.
No arbitrary SQL field names or order expressions are accepted.
"""
from __future__ import annotations

from typing import Literal
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthContext, require_permission
from app.db.session import get_db
from app.models.student import Student
from app.models.intervention import InterventionLog
from app.services.object_index_filters import compile_filters

router = APIRouter(prefix="/object-index", tags=["Object Index"])

StudentSort = Literal["name_asc", "name_desc", "risk_desc", "risk_asc", "course_asc"]
StudentView = Literal["todos", "risco", "sem_classificacao", "dados_insuficientes", "acompanhamento"]

def _student_filters(
    tenant_id: str, *, q: str | None, course: str | None,
    risk_level: str | None, view: StudentView,
):
    """Static SQL expressions, always ANDed with the authenticated tenant."""
    filters = [Student.tenant_id == tenant_id]
    if q:
        term = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        filters.append(or_(
            Student.nome.ilike(term, escape="\\"), Student.matricula.ilike(term, escape="\\"),
            Student.curso.ilike(term, escape="\\"),
        ))
    if course:
        filters.append(Student.curso == course)
    if risk_level:
        filters.append(Student.risk_level == risk_level)
    if view == "risco":
        filters.append(Student.risk_level.in_(("critico", "medio")))
    elif view == "sem_classificacao":
        filters.append(Student.risk_level.is_(None))
    elif view == "dados_insuficientes":
        filters.append(Student.risk_score.is_(None))
    elif view == "acompanhamento":
        filters.append(exists(select(InterventionLog.id).where(
            InterventionLog.tenant_id == tenant_id,
            InterventionLog.student_id == Student.id,
        )))
    return filters

def _student_sort(sort: StudentSort):
    # Nulls always at the end for score, even when descending.
    return {
        "name_asc": (Student.nome.asc(), Student.id.asc()),
        "name_desc": (Student.nome.desc(), Student.id.asc()),
        "risk_desc": (Student.risk_score.desc().nullslast(), Student.id.asc()),
        "risk_asc": (Student.risk_score.asc().nullslast(), Student.id.asc()),
        "course_asc": (Student.curso.asc().nullslast(), Student.nome.asc(), Student.id.asc()),
    }[sort]

@router.get("/students")
async def index_students(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=1000000),
    q: str | None = Query(default=None, max_length=160),
    course: str | None = Query(default=None, max_length=150),
    risk_level: Literal["critico", "medio", "baixo"] | None = None,
    view: StudentView = "todos",
    filters: str | None = Query(default=None, max_length=2000),
    sort: StudentSort = "name_asc",
    auth: AuthContext = Depends(require_permission("students.view")),
    db: AsyncSession = Depends(get_db),
):
    # Effective RBAC controls response fields AND the ability to infer a
    # student's private risk from sorting, counts or predicates.
    sensitive = (
        "students.sensitive.view" in auth.permissions
        if auth.permissions is not None else
        auth.custom_role_id is None and auth.role in ("admin", "coordinator")
    )
    compiled = compile_filters(filters)
    if not sensitive:
        sensitive_views = {"risco", "sem_classificacao", "dados_insuficientes", "acompanhamento"}
        forbidden = bool(risk_level) or view in sensitive_views or sort.startswith("risk_")
        if filters:
            filters_data = json.loads(filters)  # validated by compile_filters()
            forbidden = forbidden or any(
                item["key"] not in {"nome", "matricula", "curso"}
                for item in filters_data
            )
        if forbidden:
            raise HTTPException(status_code=403, detail="Filtros e ordenação sensíveis não autorizados.")
    scoped = _student_filters(auth.tenant_id, q=q, course=course, risk_level=risk_level, view=view)
    scoped.extend(compiled)
    total = (await db.execute(select(func.count(Student.id)).where(and_(*scoped)))).scalar_one()
    # All row access is bound to the same tenant as the count. No client-provided ID list.
    rows = (await db.execute(
        select(Student).where(and_(*scoped))
        .order_by(*_student_sort(sort)).offset(offset).limit(limit)
    )).scalars().all()
    ids = [row.id for row in rows]
    latest: dict[str, dict] = {}
    if ids and sensitive:
        ranked = (select(
            InterventionLog.student_id,
            InterventionLog.status,
            InterventionLog.created_at,
            func.row_number().over(
                partition_by=InterventionLog.student_id,
                order_by=(InterventionLog.created_at.desc(), InterventionLog.id.desc()),
            ).label("rn"),
        ).where(
            InterventionLog.tenant_id == auth.tenant_id,
            InterventionLog.student_id.in_(ids),
        )).subquery()
        result = await db.execute(select(ranked.c.student_id, ranked.c.status, ranked.c.created_at).where(ranked.c.rn == 1))
        latest = {student_id: {"status": status, "created_at": created_at.isoformat() if created_at else None}
                  for student_id, status, created_at in result}
    return {
        "students": [{
            "id": student.id, "nome": student.nome, "matricula": student.matricula,
            "curso": student.curso,
            **({
                "risk_level": student.risk_level,
                "risk_score": student.risk_score,
                "shap_summary": (student.shap_top_factors or {}).get("summary"),
                "shap_top_factors": student.shap_top_factors,
                "follow_up": latest.get(student.id),
            } if sensitive else {}),
        } for student in rows],
        "total": total, "limit": limit, "offset": offset,
        "has_more": offset + len(rows) < total,
        "scope": "tenant", "sort": sort,
    }
