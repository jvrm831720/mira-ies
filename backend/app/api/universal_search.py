"""Wave 6: bounded, tenant-scoped, RBAC-filtered federated *navigation* search.

The server returns minimal projections, never full records, phone/email, risk,
payment data, campaign rules, or saved-view configurations. The palette only
navigates; it does not execute operations.
"""
from __future__ import annotations

import asyncio
import logging
import unicodedata
from difflib import SequenceMatcher
from typing import Any, Callable
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.object_views import PERMISSION as VIEW_PERMISSION, has_permission
from app.core.auth import AuthContext, get_current_tenant
from app.db.session import get_db
from app.models.object_view import ObjectView
from app.models.retention_campaign import RetentionCampaign
from app.models.student import Student
from app.models.work_activity import WorkActivity

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/search", tags=["Busca Universal"])
PROVIDERS = ("students", "collections", "work", "views", "campaigns")
MAX_PER_PROVIDER = 6
MAX_FUZZY_CANDIDATES = 80
MAX_RESULTS = len(PROVIDERS) * MAX_PER_PROVIDER
# The text is never assembled as SQL or returned in diagnostic errors.


def normalized(value: str) -> str:
    text_value = unicodedata.normalize("NFKD", value.strip().casefold())
    return "".join(char for char in text_value if not unicodedata.combining(char))


def escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def relevance(query: str, *values: str | None) -> tuple[int, str]:
    """Explanations are strictly lexical; no inference of risk, debt or propensity."""
    term = normalized(query)
    score, label = 0, "approximate"
    for value in values:
        word = normalized(value or "")
        if not word:
            continue
        if word == term:
            candidate = (100, "exact")
        elif word.startswith(term):
            candidate = (92, "prefix")
        elif term in word:
            candidate = (84, "contains")
        elif len(term) >= 4:
            # Fuzzy matching only within bounded, tenant-scoped SQL candidates.
            ratio = SequenceMatcher(None, term, word[: max(len(term) + 4, 14)]).ratio()
            candidate = (int(70 * ratio), "approximate") if ratio >= 0.68 else (0, "approximate")
        else:
            candidate = (0, "approximate")
        if candidate[0] > score:
            score, label = candidate
    return score, label


def permitted(auth: AuthContext, provider: str) -> bool:
    # API keys, revoked/old user tokens and workspaces without a human session
    # cannot inspect an aggregate index.
    if not auth.user_id or not auth.session_id:
        return False
    if provider == "students":
        return has_permission(auth, "students.view")
    if provider == "collections":
        return has_permission(auth, "audit.view")
    if provider == "work":
        return has_permission(auth, "students.view") and (
            auth.permissions is not None or auth.role in ("operator", "coordinator", "admin")
        )
    if provider == "campaigns":
        return has_permission(auth, "campaigns.view")
    if provider == "views":
        return any(has_permission(auth, p) for p in VIEW_PERMISSION.values())
    return False


def _page_for_view(object_key: str) -> str | None:
    # Never invent a route or expose an unsupported view configuration.
    return {
        "students": "/alunos", "collections": "/cobranca",
        "campaigns": "/campanhas", "academic_classes": "/academico",
        "academic_programs": "/academico", "academic_subjects": "/academico",
        "academic_teachers": "/academico", "academic_terms": "/academico",
    }.get(object_key)


def _item(
    provider: str, identifier: str, title: str, subtitle: str, href: str,
    query: str, *aliases: str | None,
) -> dict[str, Any] | None:
    rank, matched_by = relevance(query, title, *aliases)
    if rank == 0:
        return None
    return {
        "provider": provider, "id": identifier, "title": title,
        "subtitle": subtitle[:140], "href": href,
        "rank": rank, "match": matched_by,
        "action": "navigate",
    }


async def _orm_candidates(
    db: AsyncSession, base_query, columns: tuple, query: str, sort_column,
    limit: int,
) -> list:
    """Exact matches first; fuzzy comparisons use at most 80 tenant-filtered candidates."""
    escaped = escape_like(query.strip())
    exact = base_query.where(or_(*(
        col.ilike("%" + escaped + "%", escape="\\") for col in columns
    )))
    first = (await db.execute(exact.order_by(sort_column.desc()).limit(limit * 4))).all()
    if len(first) >= limit * 4 or len(query.strip()) < 4:
        return first
    # A conservative two-character prefix pool, not an unbounded table scan.
    # This approximation is best-effort for older records outside the cap.
    prefix = escape_like(query.strip()[:2])
    fuzzy = base_query.where(or_(*(
        col.ilike(prefix + "%", escape="\\") for col in columns
    )))
    rest = (await db.execute(fuzzy.order_by(sort_column.desc()).limit(
        MAX_FUZZY_CANDIDATES
    ))).all()
    seen: set[str] = set()
    combined = []
    for row in [*first, *rest]:
        ident = str(row[0])
        if ident not in seen:
            seen.add(ident)
            combined.append(row)
    return combined


async def _students(db: AsyncSession, auth: AuthContext, query: str, limit: int) -> list[dict]:
    base = select(Student.id, Student.nome, Student.matricula, Student.curso).where(
        Student.tenant_id == auth.tenant_id
    )
    rows = await _orm_candidates(
        db, base, (Student.nome, Student.matricula), query, Student.updated_at, limit
    )
    return [
        item for row in rows if (item := _item(
            "students", row.id, row.nome, "Matrícula " + row.matricula +
            (" · " + row.curso if row.curso else ""),
            "/alunos/" + quote(row.id, safe=""), query, row.matricula,
        ))
    ]


async def _work(db: AsyncSession, auth: AuthContext, query: str, limit: int) -> list[dict]:
    base = select(WorkActivity.id, WorkActivity.title, WorkActivity.status).where(
        WorkActivity.tenant_id == auth.tenant_id
    )
    rows = await _orm_candidates(
        db, base, (WorkActivity.title,), query, WorkActivity.updated_at, limit
    )
    return [
        item for row in rows if (item := _item(
            "work", row.id, row.title, "Atividade humana · " + row.status,
            "/trabalho?activity=" + quote(row.id, safe=""), query,
        ))
    ]


async def _campaigns(db: AsyncSession, auth: AuthContext, query: str, limit: int) -> list[dict]:
    base = select(
        RetentionCampaign.id, RetentionCampaign.name, RetentionCampaign.slug,
        RetentionCampaign.version, RetentionCampaign.status,
    ).where(
        RetentionCampaign.tenant_id == auth.tenant_id,
        RetentionCampaign.archived.is_(False),
    )
    rows = await _orm_candidates(
        db, base, (RetentionCampaign.name, RetentionCampaign.slug),
        query, RetentionCampaign.updated_at, limit,
    )
    return [
        item for row in rows if (item := _item(
            "campaigns", row.id, row.name,
            f"Campanha de permanência · v{row.version} · {row.status}",
            "/campanhas", query, row.slug,
        ))
    ]


async def _views(db: AsyncSession, auth: AuthContext, query: str, limit: int) -> list[dict]:
    # The Wave 3 RLS policy uses a transaction-local sensitivity flag.
    await db.execute(text("SELECT set_config('app.view_sensitive', :value, true)"), {
        "value": "1" if has_permission(auth, "students.sensitive.view") else "0",
    })
    authorized_types = tuple(
        key for key, permission in VIEW_PERMISSION.items()
        if has_permission(auth, permission) and _page_for_view(key)
    )
    if not authorized_types:
        return []
    base = select(
        ObjectView.id, ObjectView.name, ObjectView.object_key, ObjectView.scope,
    ).where(
        ObjectView.tenant_id == auth.tenant_id,
        ObjectView.object_key.in_(authorized_types),
        or_(ObjectView.owner_user_id == auth.user_id, ObjectView.scope == "workspace"),
    )
    if not has_permission(auth, "students.sensitive.view"):
        base = base.where(ObjectView.is_sensitive.is_(False))
    rows = await _orm_candidates(db, base, (ObjectView.name,), query, ObjectView.updated_at, limit)
    result = []
    for row in rows:
        pathname = _page_for_view(row.object_key)
        if not pathname:
            continue
        href = pathname + "?saved_view=" + quote(row.id, safe="")
        item = _item(
            "views", row.id, row.name,
            f"Visualização {row.scope} · {row.object_key}", href, query,
        )
        if item:
            result.append(item)
    return result


async def _collections(db: AsyncSession, auth: AuthContext, query: str, limit: int) -> list[dict]:
    from app.services.dispatch_core import bind_tenant

    await bind_tenant(db, auth.tenant_id)
    escaped = escape_like(query.strip())
    params = {"tenant": auth.tenant_id, "q": "%" + escaped + "%",
              "prefix": escape_like(query.strip()[:2]) + "%", "cap": limit * 4,
              "fuzzy_cap": MAX_FUZZY_CANDIDATES}
    sql = """SELECT id, external_ref, subject_ref, status, source
             FROM dispatch_obligations WHERE tenant_id = :tenant
             AND (external_ref ILIKE :q OR subject_ref ILIKE :q)
             ORDER BY updated_at DESC, id DESC LIMIT :cap"""
    first = (await db.execute(text(sql), params)).mappings().all()
    extra = []
    if len(first) < limit * 4 and len(query.strip()) >= 4:
        fuzzy_sql = """SELECT id, external_ref, subject_ref, status, source
                       FROM dispatch_obligations WHERE tenant_id = :tenant
                       AND (external_ref ILIKE :prefix OR subject_ref ILIKE :prefix)
                       ORDER BY updated_at DESC, id DESC LIMIT :fuzzy_cap"""
        extra = (await db.execute(text(fuzzy_sql), params)).mappings().all()
    items = []
    seen: set[str] = set()
    for row in [*first, *extra]:
        ident = str(row["id"])
        if ident in seen:
            continue
        seen.add(ident)
        item = _item(
            "collections", ident, row["external_ref"] or "Caso financeiro",
            "Caso financeiro · " + str(row["status"]),
            "/cobranca/casos/" + quote(ident, safe=""), query, row["subject_ref"],
        )
        if item:
            items.append(item)
    return items


_SEARCHERS: dict[str, Callable] = {
    "students": _students, "collections": _collections,
    "work": _work, "views": _views, "campaigns": _campaigns,
}


@router.get("")
async def federated_search(
    q: str = Query(min_length=2, max_length=80),
    per_provider: int = Query(5, ge=1, le=MAX_PER_PROVIDER),
    auth: AuthContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    if not auth.user_id or not auth.session_id:
        raise HTTPException(status_code=403, detail="Busca federada exige sessão humana.")
    if len(q.strip()) < 2:
        raise HTTPException(status_code=422, detail="Informe pelo menos dois caracteres.")
    enabled = [name for name in PROVIDERS if permitted(auth, name)]
    results: list[dict] = []
    unavailable: list[str] = []
    for provider in enabled:
        try:
            # A SAVEPOINT lets the next provider proceed after DB timeouts/errors.
            # Low per-provider budget prevents one source from stalling all others.
            async with db.begin_nested():
                await db.execute(text("SELECT set_config('statement_timeout', '400ms', true)"))
                matched = await _SEARCHERS[provider](db, auth, q.strip(), per_provider)
            results.extend(sorted(matched, key=lambda item: (
                -item["rank"], item["title"].casefold(), item["id"]
            ))[:per_provider])
        except (Exception, asyncio.CancelledError) as exc:
            # Never surface exceptions, SQL, identifiers or raw source values.
            logger.warning("Federated search provider %s unavailable (%s)", provider, type(exc).__name__)
            unavailable.append(provider)
    # No global total: provider candidate pools are intentionally bounded.
    results.sort(key=lambda item: (
        -item["rank"], PROVIDERS.index(item["provider"]), item["title"].casefold(), item["id"]
    ))
    return {
        "query": q.strip(), "results": results[:MAX_RESULTS],
        "providers": enabled, "unavailable": unavailable,
        "partial": bool(unavailable), "count_scope": "bounded_matches",
        "per_provider_limit": per_provider,
    }
