"""Universal search is a read-only federation over existing protected objects.

Each provider owns its row projection and authorization. A database savepoint
contains provider errors (including timeouts), so no failed provider leaks
partial rows or aborts the other categories.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthContext, get_current_tenant
from app.db.session import get_db
from app.services.federated_search_providers import ORDER, PROVIDERS, SearchContext

router = APIRouter(prefix="/search", tags=["Busca Universal"])
Category = Literal["students", "collections", "work", "views", "campaigns"]

# Input size, provider count and SQL execution time are independent hard caps.
MAX_QUERY_LENGTH = 80
MAX_PROVIDERS = len(ORDER)
MAX_PROVIDER_RESULTS = 8
PROVIDER_STATEMENT_TIMEOUT_MS = 500


def parse_providers(raw: str | None) -> tuple[str, ...]:
    if raw is None:
        return ORDER
    names = [part.strip() for part in raw.split(",")]
    if not names or len(names) > MAX_PROVIDERS or any(
        name not in PROVIDERS or not name for name in names
    ) or len(set(names)) != len(names):
        raise HTTPException(status_code=422, detail="Lista de provedores inválida.")
    return tuple(name for name in ORDER if name in names)


@router.get("/universal")
async def search_universal(
    q: str = Query(..., min_length=2, max_length=MAX_QUERY_LENGTH),
    limit: int = Query(5, ge=1, le=MAX_PROVIDER_RESULTS),
    providers: str | None = Query(None, max_length=80),
    auth: AuthContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    if not auth.user_id or not auth.session_id or auth.aal < 2:
        raise HTTPException(status_code=403, detail="Busca universal exige sessão humana autenticada.")
    needle = q.strip()
    if len(needle) < 2:
        raise HTTPException(status_code=422, detail="Digite ao menos dois caracteres.")
    requested = parse_providers(providers)
    context = SearchContext(auth=auth, db=db, query=needle, limit=limit)
    entries: list[dict] = []
    statuses: dict[str, dict] = {}

    # Never use gather() with a shared AsyncSession. The transaction also holds
    # auth context used by FORCE RLS policies.
    for category in requested:
        try:
            async with db.begin_nested():
                await db.execute(text(
                    f"SET LOCAL statement_timeout = '{PROVIDER_STATEMENT_TIMEOUT_MS}ms'"
                ))
                result = await PROVIDERS[category](context)
                # Limit at the federation boundary even if a provider regresses.
                rows = result[:limit]
            entries.extend(rows)
            statuses[category] = {"status": "ok", "returned": len(rows)}
        except SQLAlchemyError:
            # No exception text or SQL details may reach the client.
            statuses[category] = {"status": "unavailable", "returned": 0}

    entries.sort(key=lambda value: (
        -value["score"], ORDER.index(value["category"]), value["title"].casefold(), value["id"]
    ))
    return {
        "query": needle, "results": entries[:MAX_PROVIDER_RESULTS * MAX_PROVIDERS],
        "providers": statuses, "partial": any(
            value["status"] != "ok" for value in statuses.values()
        ),
        "as_of": datetime.now(timezone.utc).isoformat(),
        "returned": len(entries),
        "limit_per_provider": limit,
        "count_scope": "bounded_matches_only",
        "navigation_provider": "client_permission_filtered",
        "actions_executed": False,
    }
