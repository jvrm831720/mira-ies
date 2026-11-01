"""APIs de Inteligência de Sinais — catálogo, avaliação e resumo sob demanda."""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthContext, require_min_role
from app.db.session import get_db
from app.models.student import Student
from app.signals.catalog import list_catalog
from app.signals.evaluate import evaluate_student_signals, serialize_evaluation

router = APIRouter(prefix="/signals", tags=["Inteligência de Sinais"])
logger = logging.getLogger(__name__)


def _student_snapshot(s: Student) -> dict:
    return {
        "id": s.id,
        "risk_level": s.risk_level,
        "risk_score": s.risk_score,
        "dias_atraso_boleto": s.dias_atraso_boleto,
        "dias_sem_login": s.dias_sem_login,
    }


async def _load_assessments(
    db: AsyncSession,
    *,
    tenant_id: str,
    student_id: str,
    limit: int = 2,
) -> tuple[list[dict], bool]:
    """Retorna (assessments, history_unavailable)."""
    try:
        from app.models.risk_assessment import RiskAssessment

        result = await db.execute(
            select(RiskAssessment)
            .where(
                RiskAssessment.tenant_id == tenant_id,
                RiskAssessment.student_id == student_id,
            )
            .order_by(RiskAssessment.evaluated_at.desc())
            .limit(limit)
        )
        rows = list(result.scalars().all())
        return [
            {
                "score": r.score,
                "risk_level": r.risk_level,
                "model_version": r.model_version,
                "score_semantics_version": r.score_semantics_version,
                "evaluated_at": r.evaluated_at.isoformat() if r.evaluated_at else None,
            }
            for r in rows
        ], False
    except Exception as exc:
        logger.warning(
            "signals_risk_history_unavailable tenant=%s student=%s err=%s",
            tenant_id,
            student_id,
            type(exc).__name__,
        )
        return [], True


@router.get("/catalog")
async def signals_catalog(
    auth: AuthContext = Depends(require_min_role("viewer")),
):
    items = list_catalog()
    return {
        "count": len(items),
        "catalog_version": "1.0.0",
        "signals": items,
        "tenant_id": auth.tenant_id,
    }


@router.get("/evaluate")
async def signals_evaluate(
    student_id: str = Query(..., min_length=1, max_length=64),
    auth: AuthContext = Depends(require_min_role("viewer")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Student).where(
            Student.id == student_id,
            Student.tenant_id == auth.tenant_id,
            Student.is_active.is_(True),
        )
    )
    student = result.scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="Aluno não encontrado neste tenant.")

    assessments, hist_unavail = await _load_assessments(
        db, tenant_id=auth.tenant_id, student_id=student.id
    )
    evaluation = evaluate_student_signals(
        student_id=student.id,
        tenant_id=auth.tenant_id,
        student=_student_snapshot(student),
        assessments=assessments,
        history_unavailable=hist_unavail,
    )
    return {
        "student_id": evaluation.student_id,
        "tenant_id": evaluation.tenant_id,
        "evaluated_at": evaluation.evaluated_at,
        "active_signal_ids": evaluation.active_ids(),
        "signals": [serialize_evaluation(s) for s in evaluation.signals],
    }


@router.get("/summary")
async def signals_summary(
    limit: int = Query(500, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    auth: AuthContext = Depends(require_min_role("viewer")),
    db: AsyncSession = Depends(get_db),
):
    """Resumo tenant-scoped. Um aluno pode ter vários sinais; totais de alunos são únicos."""
    total_q = await db.execute(
        select(Student.id).where(
            Student.tenant_id == auth.tenant_id,
            Student.is_active.is_(True),
        )
    )
    all_ids = [row[0] for row in total_q.all()]
    total_students = len(all_ids)

    page_q = await db.execute(
        select(Student)
        .where(
            Student.tenant_id == auth.tenant_id,
            Student.is_active.is_(True),
        )
        .order_by(Student.updated_at.desc())
        .offset(offset)
        .limit(limit)
    )
    students = list(page_q.scalars().all())

    by_signal: dict[str, int] = {}
    by_category_activations: dict[str, int] = {}
    students_with_active = 0
    students_without_active = 0
    students_with_any_insufficient = 0
    evaluated = 0

    from app.signals.catalog import SIGNAL_CATALOG

    for s in students:
        assessed, hist_unavail = await _load_assessments(
            db, tenant_id=auth.tenant_id, student_id=s.id
        )
        evaluation = evaluate_student_signals(
            student_id=s.id,
            tenant_id=auth.tenant_id,
            student=_student_snapshot(s),
            assessments=assessed,
            history_unavailable=hist_unavail,
        )
        evaluated += 1
        active = [sig for sig in evaluation.signals if sig.active]
        insufficient = [sig for sig in evaluation.signals if sig.insufficient_data]
        if active:
            students_with_active += 1
        else:
            students_without_active += 1
        if insufficient:
            students_with_any_insufficient += 1
        for sig in active:
            by_signal[sig.signal_id] = by_signal.get(sig.signal_id, 0) + 1
            cat = str(SIGNAL_CATALOG[sig.signal_id]["category"])
            by_category_activations[cat] = by_category_activations.get(cat, 0) + 1

    return {
        "tenant_id": auth.tenant_id,
        "total_students_in_tenant": total_students,
        "page": {"limit": limit, "offset": offset, "returned": evaluated},
        "students_evaluated": evaluated,
        "students_with_active_signals": students_with_active,
        "students_without_active_signals": students_without_active,
        "students_with_insufficient_data_on_any_signal": students_with_any_insufficient,
        "activations_by_signal": by_signal,
        "activations_by_category": by_category_activations,
        "notes": [
            "students_* contam alunos únicos na página avaliada.",
            "activations_by_category soma ativações, não alunos únicos (um aluno pode contribuir em várias categorias).",
            "Alunos fora do limit/offset não entram nas contagens da página.",
        ],
    }
