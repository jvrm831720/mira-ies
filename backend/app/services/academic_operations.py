"""Deterministic academic decisions. The database, not an LLM, owns outcomes."""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP


class AcademicRuleViolation(ValueError):
    pass


def validate_curriculum_graph(items: list[dict]) -> None:
    """Reject missing references, duplicated subjects and cycles."""
    edges: dict[str, str | None] = {}
    terms: dict[str, int] = {}
    for item in items:
        sid = str(item["subject_id"])
        if sid in edges:
            raise AcademicRuleViolation("Disciplina duplicada no currículo.")
        edges[sid] = str(item["prerequisite_subject_id"]) if item.get("prerequisite_subject_id") else None
        terms[sid] = int(item["period_number"])
    if not edges:
        raise AcademicRuleViolation("Um currículo precisa ter disciplinas.")
    for subject, requirement in edges.items():
        if requirement is not None:
            if requirement not in edges:
                raise AcademicRuleViolation("Pré-requisito não pertence ao currículo.")
            if terms[requirement] >= terms[subject]:
                raise AcademicRuleViolation("Pré-requisito deve pertencer a um período anterior.")
    for subject in edges:
        visited = set()
        current = subject
        while current is not None:
            if current in visited:
                raise AcademicRuleViolation("Dependências curriculares cíclicas.")
            visited.add(current)
            current = edges[current]


def policy_snapshot(policy) -> dict:
    return {
        "version": policy.version,
        "passing_percent": str(policy.passing_percent),
        "min_attendance_percent": str(policy.min_attendance_percent),
        "max_classes_per_term": policy.max_classes_per_term,
        "excused_excluded": bool(policy.excused_excluded),
        "allow_reenrollment": bool(policy.allow_reenrollment),
        "enrollment_opens_on": (policy.enrollment_opens_on.isoformat()
                                if policy.enrollment_opens_on else None),
        "enrollment_closes_on": (policy.enrollment_closes_on.isoformat()
                                 if policy.enrollment_closes_on else None),
    }


def enrollment_in_window(policy, today) -> bool:
    if policy.enrollment_opens_on and today < policy.enrollment_opens_on:
        return False
    if policy.enrollment_closes_on and today > policy.enrollment_closes_on:
        return False
    return True


def calculate_result(
    grades: list[tuple[Decimal, Decimal, bool]],
    attendance: list[str | None],
    *,
    passing_percent: Decimal,
    min_attendance_percent: Decimal,
    excused_excluded: bool,
) -> dict:
    """Grade triples = (score, max_score, published). Missing means incomplete.

    Attendance one entry per *published* lesson; None/unrecorded is unknown.
    Excused entries are excluded from denominator only when policy says so.
    """
    if not grades or not attendance:
        return {"ready": False, "reason": "Sem avaliações ou aulas publicadas."}
    if any(not published or max_score <= 0 or score < 0 or score > max_score
           for score, max_score, published in grades):
        return {"ready": False, "reason": "Existem notas ausentes, inválidas ou não publicadas."}
    if any(status is None or status == "unrecorded" or
           status not in ("present", "absent", "excused") for status in attendance):
        return {"ready": False, "reason": "Chamada incompleta; nenhuma presença presumida."}
    denominator = sum((maximum for _, maximum, _ in grades), Decimal("0"))
    score = sum((mark for mark, _, _ in grades), Decimal("0"))
    if denominator <= 0:
        return {"ready": False, "reason": "Não há pontuação máxima válida."}
    counted = [s for s in attendance if not (s == "excused" and excused_excluded)]
    if not counted:
        return {"ready": False, "reason": "Não há aulas computáveis para frequência."}
    score_pct = (score / denominator * Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    present = sum(1 for status in counted if status == "present")
    attendance_pct = (Decimal(present) / Decimal(len(counted)) * Decimal("100")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP,
    )
    passed = score_pct >= passing_percent and attendance_pct >= min_attendance_percent
    return {
        "ready": True, "score_percent": str(score_pct),
        "attendance_percent": str(attendance_pct),
        "result": "passed" if passed else "failed",
        "grade_criterion_met": score_pct >= passing_percent,
        "attendance_criterion_met": attendance_pct >= min_attendance_percent,
    }
