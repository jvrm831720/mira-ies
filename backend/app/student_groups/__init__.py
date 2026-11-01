"""Motor de grupos virtuais de alunos da Wave 2.2."""

from app.student_groups.catalog import GROUP_DEFINITIONS, GROUP_CATALOG_VERSION
from app.student_groups.evaluate import evaluate_student_groups

__all__ = ["GROUP_DEFINITIONS", "GROUP_CATALOG_VERSION", "evaluate_student_groups"]
