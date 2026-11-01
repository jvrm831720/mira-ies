"""Endpoints do motor virtual de grupos de alunos (Wave 2.2)."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthContext, require_min_role
from app.db.session import get_db
from app.models.student import Student
from app.student_groups.catalog import (
    GROUP_CATALOG_VERSION,
    GROUP_DEFINITIONS,
    serialize_catalog_item,
)
from app.student_groups.evaluate import evaluate_student_groups
from app.student_groups.loading import (
    GROUP_BATCH_SIZE,
    GROUP_MAX_STUDENTS,
    iter_student_group_batches,
    student_snapshot,
)

router = APIRouter(prefix="/student-groups", tags=["Grupos virtuais de alunos"])


@router.get("/catalog")
async def student_groups_catalog(
    auth: AuthContext = Depends(require_min_role("viewer")),
):
    return {
        "catalog_version": GROUP_CATALOG_VERSION,
        "count": len(GROUP_DEFINITIONS),
        "groups": [serialize_catalog_item(item) for item in GROUP_DEFINITIONS],
        "scope": "active_students_in_authenticated_tenant",
        "tenant_id": auth.tenant_id,
        "notes": [
            "Grupos são derivados sob demanda e não persistem associações de alunos.",
            "missing_score é uma lacuna de cobertura, não um grupo de baixo risco.",
        ],
    }


@router.get("/summary")
async def student_groups_summary(
    auth: AuthContext = Depends(require_min_role("viewer")),
    db: AsyncSession = Depends(get_db),
):
    evaluated_at = datetime.now(timezone.utc).isoformat()
    total_eligible = int(
        (
            await db.execute(
                select(func.count())
                .select_from(Student)
                .where(Student.tenant_id == auth.tenant_id, Student.is_active.is_(True))
            )
        ).scalar_one()
        or 0
    )
    counts = {
        item.id: {"matched_count": 0, "false_count": 0, "indeterminate_count": 0}
        for item in GROUP_DEFINITIONS
    }
    evaluated = 0
    history_unavailable_batches = 0

    try:
        async for batch in iter_student_group_batches(db, tenant_id=auth.tenant_id):
            if batch.history_unavailable:
                history_unavailable_batches += 1
            for student in batch.students:
                result = evaluate_student_groups(
                    student_id=student.id,
                    tenant_id=auth.tenant_id,
                    student=student_snapshot(student),
                    assessments=batch.assessments_by_student.get(student.id, []),
                    history_unavailable=batch.history_unavailable,
                    evaluated_at=datetime.fromisoformat(evaluated_at),
                )
                for group in result.groups:
                    bucket = counts[group.group_id]
                    if group.state == "TRUE":
                        bucket["matched_count"] += 1
                    elif group.state == "FALSE":
                        bucket["false_count"] += 1
                    else:
                        bucket["indeterminate_count"] += 1
                evaluated += 1
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Não foi possível avaliar os grupos neste momento.",
        ) from exc

    truncated = evaluated < total_eligible
    groups = []
    for definition in GROUP_DEFINITIONS:
        bucket = counts[definition.id]
        groups.append(
            {
                "id": definition.id,
                "name": definition.name,
                "matched_count": bucket["matched_count"],
                "false_count": bucket["false_count"],
                "indeterminate_count": bucket["indeterminate_count"],
                "coverage": {
                    "evaluated": evaluated,
                    "eligible": total_eligible,
                    "complete": not truncated and bucket["indeterminate_count"] == 0,
                    "has_indeterminate": bucket["indeterminate_count"] > 0,
                },
                "limitations": list(definition.limitations),
            }
        )
    notes = [
        "matched_count conta somente alunos com estado TRUE; false_count conta somente FALSE.",
        "indeterminate_count não é somado a matched_count nem a false_count.",
        "Contagens entre grupos não são mutuamente exclusivas e representam alunos únicos por grupo.",
        "Escopo de elegibilidade: somente alunos ativos do tenant autenticado.",
        f"Limite provisório configurável: {GROUP_MAX_STUDENTS} alunos por request; truncated=true quando excedido.",
        f"Tamanho provisório configurável do lote: {GROUP_BATCH_SIZE} alunos; não é SLO de produção.",
    ]
    if history_unavailable_batches:
        notes.append(
            "Um ou mais lotes não puderam carregar histórico; risk_increase e grupos dependentes preservam INDETERMINATE."
        )
    return {
        "evaluated_at": evaluated_at,
        "scope": "active_students_in_authenticated_tenant",
        "total_eligible": total_eligible,
        "evaluated": evaluated,
        "groups": groups,
        "truncated": truncated,
        "notes": notes,
    }
