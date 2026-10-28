"""Implementação das consultas de histórico de risco."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthContext
from app.models.student import Student
from app.models.risk_assessment import RiskAssessment
from app.models.intervention import InterventionLog

_VALID_RISK_LEVELS = {"baixo", "medio", "critico"}


def _utc(value: datetime | None, fallback: datetime) -> datetime:
    if value is None:
        return fallback
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _assessment_payload(row: RiskAssessment, student: Student | None = None) -> dict[str, Any]:
    return {
        "id": row.id,
        "student_id": row.student_id,
        "tenant_id": row.tenant_id,
        "student_name": student.nome if student else None,
        "matricula": student.matricula if student else None,
        "course": student.curso if student else None,
        "evaluated_at": row.evaluated_at.isoformat(),
        "score": row.score,
        "risk_level": row.risk_level,
        "model_version": row.model_version,
        "score_semantics_version": row.score_semantics_version,
        "score_basis": row.score_basis,
        "model_scope": row.model_scope,
        "model_score": row.model_score,
        "dynamic_adjustment": row.dynamic_adjustment,
        "explanation": row.explanation if row.explanation and row.explanation.get("available") else None,
        "explanation_available": bool(row.explanation and row.explanation.get("available")),
        "scoring_run_id": row.scoring_run_id,
        "batch_id": row.batch_id,
    }


def _change_type(current: RiskAssessment, previous: RiskAssessment | None) -> tuple[str, float | None]:
    if previous is None:
        return "sem_historico_comparavel", None
    if (
        not current.model_version
        or not previous.model_version
        or current.model_version != previous.model_version
        or current.model_scope != previous.model_scope
        or not current.score_semantics_version
        or current.score_semantics_version != previous.score_semantics_version
    ):
        return "mudanca_modelo", None
    delta = round(float(current.score) - float(previous.score), 1)
    if delta > 0:
        return "risco_aumentou", delta
    if delta < 0:
        return "risco_diminuiu", delta
    return "sem_mudanca_relevante", delta


async def risk_history(
    *,
    from_date: datetime | None,
    to_date: datetime | None,
    course: str | None,
    risk_level: str | None,
    page: int,
    page_size: int,
    auth: AuthContext,
    db: AsyncSession,
):
    """Consulta histórica; não calcula novo score. Todas as leituras são tenant-scoped."""
    now = datetime.now(timezone.utc)
    end = _utc(to_date, now)
    start = _utc(from_date, end - timedelta(days=90))
    if start >= end:
        raise HTTPException(status_code=422, detail="'from' deve ser anterior a 'to'.")
    if end - start > timedelta(days=366):
        raise HTTPException(status_code=422, detail="O período máximo de consulta é de 366 dias.")
    if risk_level and risk_level not in _VALID_RISK_LEVELS:
        raise HTTPException(status_code=422, detail="risk_level inválido.")
    course_filter = course.strip() if course and course.strip() else None
    query = select(RiskAssessment, Student).join(Student, Student.id == RiskAssessment.student_id).where(
        RiskAssessment.tenant_id == auth.tenant_id,
        Student.tenant_id == auth.tenant_id,
        RiskAssessment.evaluated_at >= start,
        RiskAssessment.evaluated_at <= end,
    )
    if course_filter:
        query = query.where(Student.curso == course_filter)
    if risk_level:
        query = query.where(RiskAssessment.risk_level == risk_level)
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
    students_total_query = (
        select(func.count(func.distinct(RiskAssessment.student_id)))
        .select_from(RiskAssessment)
        .join(Student, Student.id == RiskAssessment.student_id)
        .where(
            RiskAssessment.tenant_id == auth.tenant_id,
            Student.tenant_id == auth.tenant_id,
            RiskAssessment.evaluated_at >= start,
            RiskAssessment.evaluated_at <= end,
            *([Student.curso.ilike("%" + course_filter + "%")] if course_filter else []),
            *([RiskAssessment.risk_level == risk_level] if risk_level else []),
        )
    )
    students_total = (await db.execute(students_total_query)).scalar_one()
    page_rows = (
        await db.execute(
            query.order_by(RiskAssessment.evaluated_at.desc(), RiskAssessment.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    temporal_query = (
        select(RiskAssessment, Student)
        .join(Student, Student.id == RiskAssessment.student_id)
        .where(
            RiskAssessment.tenant_id == auth.tenant_id,
            Student.tenant_id == auth.tenant_id,
            RiskAssessment.evaluated_at >= start,
            RiskAssessment.evaluated_at <= end,
            *([Student.curso == course_filter] if course_filter else []),
        )
    )
    temporal_rows = (
        await db.execute(
            temporal_query.order_by(RiskAssessment.evaluated_at.desc(), RiskAssessment.id.desc()).limit(5000)
        )
    ).all()
    movement_query = (
        select(RiskAssessment, Student)
        .join(Student, Student.id == RiskAssessment.student_id)
        .where(
            RiskAssessment.tenant_id == auth.tenant_id,
            Student.tenant_id == auth.tenant_id,
            RiskAssessment.evaluated_at >= start,
            RiskAssessment.evaluated_at <= end,
            *([Student.curso.ilike("%" + course_filter + "%")] if course_filter else []),
        )
    )
    movement_rows = (
        await db.execute(
            movement_query.order_by(RiskAssessment.evaluated_at.desc(), RiskAssessment.id.desc()).limit(5000)
        )
    ).all()
    movement_student_by_id = {row.student_id: student for row, student in movement_rows}
    current_by_student: dict[str, RiskAssessment] = {}
    for row, _student in movement_rows:
        current_by_student.setdefault(row.student_id, row)
    previous_by_student: dict[str, RiskAssessment] = {}
    if current_by_student:
        ranked = (
            select(
                RiskAssessment.id.label("assessment_id"),
                func.row_number()
                .over(
                    partition_by=RiskAssessment.student_id,
                    order_by=(RiskAssessment.evaluated_at.desc(), RiskAssessment.id.desc()),
                )
                .label("rn"),
            )
            .where(
                RiskAssessment.tenant_id == auth.tenant_id,
                RiskAssessment.student_id.in_(list(current_by_student.keys())),
                RiskAssessment.evaluated_at <= end,
            )
            .subquery()
        )
        previous_rows = (
            await db.execute(
                select(RiskAssessment)
                .join(ranked, ranked.c.assessment_id == RiskAssessment.id)
                .where(ranked.c.rn == 2, RiskAssessment.tenant_id == auth.tenant_id)
            )
        ).scalars().all()
        previous_by_student = {row.student_id: row for row in previous_rows}
    movements = []
    counts: dict[str, int] = defaultdict(int)
    classification_changes = 0
    for student_id, current in current_by_student.items():
        if risk_level and current.risk_level != risk_level:
            continue
        previous = previous_by_student.get(student_id)
        change_type, delta = _change_type(current, previous)
        counts[change_type] += 1
        if previous and delta is not None and previous.risk_level != current.risk_level:
            classification_changes += 1
        student = movement_student_by_id.get(student_id)
        movements.append(
            {
                "student_id": student_id,
                "student_name": student.nome if student else None,
                "matricula": student.matricula if student else None,
                "course": student.curso if student else None,
                "previous_score": previous.score if previous else None,
                "previous_risk_level": previous.risk_level if previous else None,
                "previous_evaluated_at": previous.evaluated_at.isoformat() if previous else None,
                "current_score": current.score,
                "current_risk_level": current.risk_level,
                "current_evaluated_at": current.evaluated_at.isoformat(),
                "delta": delta,
                "change_type": change_type,
                "model_version": current.model_version,
                "previous_model_version": previous.model_version if previous else None,
                "score_semantics_version": current.score_semantics_version,
                "previous_score_semantics_version": previous.score_semantics_version if previous else None,
                "classification_changed": bool(
                    previous and previous.risk_level != current.risk_level and delta is not None
                ),
            }
        )
    # Timeline: last assessment per student per ISO week, grouped by model identity
    week_buckets: dict[tuple, dict[str, Any]] = {}
    latest_in_week: dict[tuple, RiskAssessment] = {}
    for row, student in temporal_rows:
        week = row.evaluated_at.astimezone(timezone.utc).strftime("%Y-%W")
        key = (week, row.model_scope, row.model_version or "", row.score_semantics_version)
        prev = latest_in_week.get((week, row.student_id))
        if prev is None or row.evaluated_at > prev.evaluated_at or (
            row.evaluated_at == prev.evaluated_at and row.id > prev.id
        ):
            latest_in_week[(week, row.student_id)] = row
            if key not in week_buckets:
                week_buckets[key] = {
                    "bucket": row.evaluated_at.astimezone(timezone.utc).replace(
                        hour=0, minute=0, second=0, microsecond=0
                    ).isoformat(),
                    "model_scope": row.model_scope,
                    "model_version": row.model_version or "",
                    "score_semantics_version": row.score_semantics_version,
                    "scores": [],
                    "levels": {"baixo": 0, "medio": 0, "critico": 0},
                }
    # Rebuild using latest_in_week
    week_buckets = {}
    for (week, student_id), row in latest_in_week.items():
        key = (week, row.model_scope, row.model_version or "", row.score_semantics_version)
        if key not in week_buckets:
            week_buckets[key] = {
                "bucket": datetime.strptime(week + "-1", "%Y-%W-%w")
                .replace(tzinfo=timezone.utc)
                .isoformat(),
                "model_scope": row.model_scope,
                "model_version": row.model_version or "",
                "score_semantics_version": row.score_semantics_version,
                "scores": [],
                "levels": {"baixo": 0, "medio": 0, "critico": 0},
            }
        week_buckets[key]["scores"].append(float(row.score))
        if row.risk_level in week_buckets[key]["levels"]:
            week_buckets[key]["levels"][row.risk_level] += 1
    timeline = []
    for key in sorted(week_buckets.keys()):
        bucket = week_buckets[key]
        scores = bucket["scores"]
        students_count = len(scores)
        timeline.append(
            {
                "bucket": bucket["bucket"],
                "model_scope": bucket["model_scope"],
                "model_version": bucket["model_version"],
                "score_semantics_version": bucket["score_semantics_version"],
                "average_score": round(sum(scores) / students_count, 1) if students_count else 0,
                "students_count": students_count,
                "risk_distribution": {
                    **bucket["levels"],
                    "students_count": students_count,
                },
            }
        )
    courses = sorted(
        {
            s.curso
            for _, s in temporal_rows
            if s.curso
        }
    )
    return {
        "tenant_id": auth.tenant_id,
        "period": {"from": start.isoformat(), "to": end.isoformat()},
        "filters": {"course": course_filter, "risk_level": risk_level},
        "total_assessments": total,
        "students_with_assessments": students_total,
        "temporal_data_truncated": len(temporal_rows) >= 5000,
        "temporal_rows_limit": 5000,
        "comparison_counts": {
            "increased": counts["risco_aumentou"],
            "decreased": counts["risco_diminuiu"],
            "unchanged": counts["sem_mudanca_relevante"],
            "model_changed": counts["mudanca_modelo"],
            "no_comparable_history": counts["sem_historico_comparavel"],
            "classification_changed": classification_changes,
        },
        "timeline": timeline,
        "courses": courses,
        "movements": movements[:500],
        "movements_truncated": len(movements) > 500 or len(movement_rows) >= 5000,
        "assessments": [
            {**_assessment_payload(row, student), "student_name": student.nome, "course": student.curso}
            for row, student in page_rows
        ],
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "pages": (total + page_size - 1) // page_size if page_size else 0,
        },
        "definition": (
            "Aumento significa delta positivo na escala 0–100 (score maior = maior risco). "
            "'Sem mudança relevante' significa delta exatamente zero; não há limiar científico configurado."
        ),
    }


async def student_risk_history(
    *,
    student_id: str,
    from_date: datetime | None,
    to_date: datetime | None,
    page: int,
    page_size: int,
    auth: AuthContext,
    db: AsyncSession,
):
    """Trajetória e intervenções do aluno autenticado; nunca recalcula scores."""
    student = (
        await db.execute(
            select(Student).where(Student.id == student_id, Student.tenant_id == auth.tenant_id)
        )
    ).scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="Aluno não encontrado.")
    now = datetime.now(timezone.utc)
    end = _utc(to_date, now)
    start = _utc(from_date, end - timedelta(days=365))
    if start >= end:
        raise HTTPException(status_code=422, detail="'from' deve ser anterior a 'to'.")
    if end - start > timedelta(days=366):
        raise HTTPException(status_code=422, detail="O período máximo de consulta é de 366 dias.")
    base = select(RiskAssessment).where(
        RiskAssessment.tenant_id == auth.tenant_id,
        RiskAssessment.student_id == student_id,
        RiskAssessment.evaluated_at >= start,
        RiskAssessment.evaluated_at <= end,
    )
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (
        await db.execute(
            base.order_by(RiskAssessment.evaluated_at.desc(), RiskAssessment.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    rows = list(reversed(rows))
    logs = (
        await db.execute(
            select(InterventionLog)
            .where(
                InterventionLog.tenant_id == auth.tenant_id,
                InterventionLog.student_id == student_id,
                InterventionLog.created_at >= start,
                InterventionLog.created_at <= end,
            )
            .order_by(InterventionLog.created_at.asc())
            .limit(200)
        )
    ).scalars().all()
    return {
        "student": {
            "id": student.id,
            "name": student.nome,
            "matricula": student.matricula,
            "course": student.curso,
            "tenant_id": auth.tenant_id,
        },
        "period": {"from": start.isoformat(), "to": end.isoformat()},
        "assessments": [_assessment_payload(row, student) for row in rows],
        "total_assessments": total,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "pages": (total + page_size - 1) // page_size if page_size else 0,
        },
        "interventions": [
            {
                "id": log.id,
                "created_at": log.created_at.isoformat(),
                "channel": log.channel,
                "status": log.status,
                "risk_score": log.risk_score,
                "risk_level": log.risk_level,
                "decision_reason": log.decision_reason,
                "outcome": log.outcome,
                "outcome_at": log.outcome_at.isoformat() if log.outcome_at else None,
            }
            for log in logs
        ],
        "explanation_note": (
            "Fatores são exibidos apenas quando foram preservados na avaliação original; "
            "nenhuma explicação histórica é recalculada nesta consulta."
        ),
    }
