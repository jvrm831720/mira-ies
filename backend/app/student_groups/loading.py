"""Leitura em lotes para avaliação de grupos sem padrão N+1 de histórico."""
from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.risk_assessment import RiskAssessment
from app.models.student import Student

logger = logging.getLogger(__name__)


def _positive_int_env(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return value if value > 0 else default


# Valores provisórios e configuráveis; não são dimensionamento de produção.
DEFAULT_GROUP_BATCH_SIZE = 250
DEFAULT_GROUP_MAX_STUDENTS = 10_000
GROUP_BATCH_SIZE = _positive_int_env("STUDENT_GROUP_BATCH_SIZE", DEFAULT_GROUP_BATCH_SIZE)
GROUP_MAX_STUDENTS = _positive_int_env("STUDENT_GROUP_MAX_STUDENTS", DEFAULT_GROUP_MAX_STUDENTS)


@dataclass(frozen=True)
class StudentGroupBatch:
    students: list["StudentSnapshot"]
    assessments_by_student: dict[str, list[dict[str, Any]]]
    history_unavailable: bool


@dataclass(frozen=True)
class StudentSnapshot:
    id: str
    risk_level: Any
    risk_score: Any
    dias_atraso_boleto: Any
    dias_sem_login: Any


def student_snapshot(student: StudentSnapshot | Student) -> dict[str, Any]:
    return {
        "id": student.id,
        "risk_level": student.risk_level,
        "risk_score": student.risk_score,
        "dias_atraso_boleto": student.dias_atraso_boleto,
        "dias_sem_login": student.dias_sem_login,
    }


def _student_query(tenant_id: str, after_id: str | None, limit: int) -> Select:
    query = (
        select(
            Student.id,
            Student.risk_level,
            Student.risk_score,
            Student.dias_atraso_boleto,
            Student.dias_sem_login,
        )
        .where(Student.tenant_id == tenant_id, Student.is_active.is_(True))
        .order_by(Student.id.asc())
        .limit(limit)
    )
    if after_id is not None:
        query = query.where(Student.id > after_id)
    return query


async def iter_student_group_batches(
    db: AsyncSession,
    *,
    tenant_id: str,
    batch_size: int = GROUP_BATCH_SIZE,
    max_students: int = GROUP_MAX_STUDENTS,
) -> AsyncIterator[StudentGroupBatch]:
    """Yield active students and at most two deterministic history rows per student.

    A batch uses one student query and one history query, both tenant-scoped. A
    history failure is represented as unavailable so callers preserve
    INDETERMINATE rather than treating a technical failure as FALSE.
    """
    after_id: str | None = None
    loaded = 0
    while loaded < max_students:
        limit = min(batch_size, max_students - loaded)
        result = await db.execute(_student_query(tenant_id, after_id, limit))
        students = [StudentSnapshot(**row) for row in result.mappings().all()]
        if not students:
            return
        student_ids = [student.id for student in students]
        history_unavailable = False
        assessments_by_student: dict[str, list[dict[str, Any]]] = {sid: [] for sid in student_ids}
        try:
            history_result = await db.execute(
                select(RiskAssessment)
                .where(
                    RiskAssessment.tenant_id == tenant_id,
                    RiskAssessment.student_id.in_(student_ids),
                )
                .order_by(
                    RiskAssessment.student_id.asc(),
                    RiskAssessment.evaluated_at.desc(),
                    RiskAssessment.id.desc(),
                )
            )
            for assessment in history_result.scalars().all():
                rows = assessments_by_student[assessment.student_id]
                if len(rows) < 2:
                    rows.append(
                        {
                            "score": assessment.score,
                            "risk_level": assessment.risk_level,
                            "model_version": assessment.model_version,
                            "score_semantics_version": assessment.score_semantics_version,
                            "evaluated_at": (
                                assessment.evaluated_at.isoformat()
                                if assessment.evaluated_at
                                else None
                            ),
                        }
                    )
        except Exception as exc:  # pragma: no cover - exercised with DB failure integration test
            logger.warning(
                "student_groups_history_unavailable tenant=%s err=%s",
                tenant_id,
                type(exc).__name__,
            )
            history_unavailable = True
            assessments_by_student = {sid: [] for sid in student_ids}
        yield StudentGroupBatch(students, assessments_by_student, history_unavailable)
        loaded += len(students)
        after_id = students[-1].id
        if len(students) < limit:
            return
