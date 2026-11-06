"""Safe, deterministic server-side multisort for tenant-scoped Object Index pages.

The client only selects field names from a static per-object allowlist.
All values are validated before assembling SQL expressions.
"""
from __future__ import annotations

from fastapi import HTTPException

STUDENT_SORT_FIELDS = frozenset({"nome", "curso", "risk_score", "matricula"})
COLLECTION_SORT_FIELDS = frozenset({"updated_at", "external_ref", "status", "balance", "source"})

def parse_sort_terms(raw: str | None, allowed: frozenset[str], *, maximum: int = 3) -> list[tuple[str, str]]:
    if raw is None or raw == "":
        return []
    if len(raw) > 256:
        raise HTTPException(status_code=422, detail="Ordenação extensa.")
    result: list[tuple[str, str]] = []
    seen: set[str] = set()
    for term in raw.split(","):
        if term.count(":") != 1:
            raise HTTPException(status_code=422, detail="Formato de ordenação inválido.")
        field, direction = term.split(":")
        if field not in allowed or direction not in ("asc", "desc") or field in seen:
            raise HTTPException(status_code=422, detail="Campo ou direção de ordenação inválido.")
        result.append((field, direction))
        seen.add(field)
        if len(result) > maximum:
            raise HTTPException(status_code=422, detail="Máximo de três ordenações.")
    return result
