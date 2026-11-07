"""Wave 6: explicit providers for bounded tenant- and permission-scoped search.

No ORM objects, model scores, payment fields, messages, or action payloads
leave the provider boundary. Only safe, clickable identity projections do.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable

from sqlalchemy import case, desc, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.object_views import PERMISSION, can_sensitive, has_permission
from app.core.auth import AuthContext
from app.models.object_view import ObjectView
from app.models.retention_campaign import RetentionCampaignProposal
from app.models.student import Student
from app.models.work_activity import WorkActivity


@dataclass(frozen=True)
class SearchContext:
    auth: AuthContext
    db: AsyncSession
    query: str
    limit: int
    operation_profile: str
    enabled_modules: frozenset[str]

    def supports(self, category: str) -> bool:
        education = self.operation_profile == "institution"
        collections_profile = self.operation_profile in (
            "collection", "debt_collection", "billing", "cobranca",
        )
        if category == "students":
            return education and "permanence" in self.enabled_modules
        if category == "collections":
            return (education or collections_profile) and "billing" in self.enabled_modules
        if category == "work":
            return "workspace" in self.enabled_modules
        if category == "campaigns":
            return (education and "permanence" in self.enabled_modules) or (
                collections_profile and "billing" in self.enabled_modules
            )
        return False

    @property
    def needle(self) -> str:
        return self.query.casefold()

    @property
    def pattern(self) -> str:
        escaped = self.needle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        return f"%{escaped}%"

    @property
    def prefix(self) -> str:
        escaped = self.needle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        return f"{escaped}%"


def allowed(auth: AuthContext, permission: str) -> bool:
    """Use the same effective grant rules as the existing saved-view API."""
    return bool(auth.user_id and auth.session_id and has_permission(auth, permission))


def eligible(expr, ctx: SearchContext):
    """SQL wildcard escaping + trigram approximate search. Both paths use indices."""
    col = func.lower(expr)
    return or_(col.ilike(ctx.pattern, escape="\\"), col.op("%")(ctx.needle))


def ranking(expr, ctx: SearchContext):
    col = func.lower(expr)
    return (
        case((col == ctx.needle, 4),
             (col.like(ctx.prefix, escape="\\"), 3),
             (col.like(ctx.pattern, escape="\\"), 2), else_=0)
        + func.similarity(col, ctx.needle)
    )


def item(*, category: str, uid: str, title: str, subtitle: str, href: str,
         score: float) -> dict:
    return {
        "category": category, "id": str(uid), "title": title,
        "subtitle": subtitle, "href": href,
        "score": round(min(5.0, max(0.0, float(score or 0))), 4),
        "kind": "navigate",
    }


async def students(ctx: SearchContext) -> list[dict]:
    if not ctx.supports("students") or not allowed(ctx.auth, "students.view"):
        return []
    name = func.coalesce(Student.nome, "")
    enrollment = func.coalesce(Student.matricula, "")
    term = func.greatest(ranking(name, ctx), ranking(enrollment, ctx))
    rows = (await ctx.db.execute(
        select(Student.id, Student.nome, Student.matricula, Student.curso,
               term.label("relevance"))
        .where(Student.tenant_id == ctx.auth.tenant_id,
               or_(eligible(name, ctx), eligible(enrollment, ctx)))
        .order_by(desc("relevance"), Student.id.asc())
        .limit(ctx.limit)
    )).all()
    return [item(
        category="students", uid=row.id, title=row.nome or "Aluno sem nome",
        subtitle="Aluno · Matrícula " + (row.matricula or "não informada") +
                 (f" · {row.curso}" if row.curso else ""),
        href="/alunos/" + row.id, score=row.relevance,
    ) for row in rows]


async def collections(ctx: SearchContext) -> list[dict]:
    if not ctx.supports("collections") or not allowed(ctx.auth, "audit.view"):
        return []
    # Source-confirmed obligations only. Do not project balances, payment evidence,
    # student data or provider payload from an aggregated search.
    rows = (await ctx.db.execute(text(r"""
        SELECT id, external_ref, subject_ref, status,
               GREATEST(
                 CASE WHEN lower(external_ref)=:needle THEN 4
                      WHEN lower(external_ref) LIKE :prefix ESCAPE '\' THEN 3
                      WHEN lower(external_ref) LIKE :pattern ESCAPE '\' THEN 2
                      ELSE 0 END + similarity(lower(external_ref), :needle),
                 CASE WHEN lower(coalesce(subject_ref,''))=:needle THEN 4
                      WHEN lower(coalesce(subject_ref,'')) LIKE :prefix ESCAPE '\' THEN 3
                      WHEN lower(coalesce(subject_ref,'')) LIKE :pattern ESCAPE '\' THEN 2
                      ELSE 0 END + similarity(lower(coalesce(subject_ref,'')), :needle)
               ) AS relevance
        FROM dispatch_obligations
        WHERE tenant_id=:tenant
          AND (
            lower(external_ref) LIKE :pattern ESCAPE '\'
            OR lower(coalesce(subject_ref,'')) LIKE :pattern ESCAPE '\'
            OR lower(external_ref) % :needle
            OR lower(coalesce(subject_ref,'')) % :needle
          )
        ORDER BY relevance DESC, id ASC LIMIT :limit
    """), {
        "tenant": ctx.auth.tenant_id, "needle": ctx.needle,
        "pattern": ctx.pattern, "prefix": ctx.prefix, "limit": ctx.limit,
    })).mappings().all()
    return [item(
        category="collections", uid=str(row["id"]),
        title=row["external_ref"] or "Caso financeiro",
        subtitle="Caso financeiro · Estado da origem: " + (row["status"] or "desconhecido") +
                 (" · Ref. " + str(row["subject_ref"]) if row["subject_ref"] else ""),
        href="/cobranca/casos/" + str(row["id"]), score=row["relevance"],
    ) for row in rows]


async def work(ctx: SearchContext) -> list[dict]:
    if not (ctx.supports("work") and allowed(ctx.auth, "access.operator") and allowed(ctx.auth, "students.view")):
        return []
    title = func.coalesce(WorkActivity.title, "")
    term = ranking(title, ctx)
    rows = (await ctx.db.execute(
        select(WorkActivity.id, WorkActivity.title, WorkActivity.status,
               WorkActivity.priority, term.label("relevance"))
        .where(WorkActivity.tenant_id == ctx.auth.tenant_id,
               eligible(title, ctx))
        .order_by(desc("relevance"), WorkActivity.id.asc())
        .limit(ctx.limit)
    )).all()
    return [item(
        category="work", uid=row.id, title=row.title,
        subtitle=f"Atividade humana · {row.status} · Prioridade {row.priority}",
        href="/trabalho?activity=" + row.id, score=row.relevance,
    ) for row in rows]


# Only object indexes currently displaying saved views in the application.
_VIEW_ROUTES = {"students": "/alunos", "collections": "/cobranca", "campaigns": "/campanhas"}
_VIEW_LABELS = {"students": "Alunos", "collections": "Casos financeiros", "campaigns": "Campanhas"}


async def views(ctx: SearchContext) -> list[dict]:
    if not ctx.auth.user_id or not ctx.auth.session_id:
        return []
    keys = [key for key in _VIEW_ROUTES if ctx.supports(key) and allowed(ctx.auth, PERMISSION[key])]
    if not keys:
        return []
    # Existing view policies also use app.view_sensitive; set in the *current*
    # transaction before loading the projection. Never return stored configs.
    await ctx.db.execute(
        text("SELECT set_config('app.view_sensitive', :access, true)"),
        {"access": "1" if can_sensitive(ctx.auth) else "0"},
    )
    name = func.coalesce(ObjectView.name, "")
    term = ranking(name, ctx)
    clauses = [
        ObjectView.tenant_id == ctx.auth.tenant_id,
        ObjectView.object_key.in_(keys),
        or_(ObjectView.owner_user_id == ctx.auth.user_id,
            ObjectView.scope == "workspace"),
        eligible(name, ctx),
    ]
    if not can_sensitive(ctx.auth):
        clauses.append(ObjectView.is_sensitive.is_(False))
    rows = (await ctx.db.execute(
        select(ObjectView.id, ObjectView.name, ObjectView.object_key,
               ObjectView.scope, term.label("relevance"))
        .where(*clauses)
        .order_by(desc("relevance"), ObjectView.id.asc())
        .limit(ctx.limit)
    )).all()
    return [item(
        category="views", uid=row.id, title=row.name,
        subtitle="View · " + _VIEW_LABELS[row.object_key] + " · " +
                 ("Compartilhada" if row.scope == "workspace" else "Pessoal"),
        href=_VIEW_ROUTES[row.object_key] + "?saved_view=" + row.id,
        score=row.relevance,
    ) for row in rows]


async def campaigns(ctx: SearchContext) -> list[dict]:
    if not ctx.supports("campaigns") or not allowed(ctx.auth, "campaigns.view"):
        return []
    name = func.coalesce(RetentionCampaignProposal.title, "")
    term = ranking(name, ctx)
    rows = (await ctx.db.execute(
        select(RetentionCampaignProposal.id, RetentionCampaignProposal.title,
               RetentionCampaignProposal.status, term.label("relevance"))
        .where(RetentionCampaignProposal.tenant_id == ctx.auth.tenant_id,
               eligible(name, ctx))
        .order_by(desc("relevance"), RetentionCampaignProposal.id.asc())
        .limit(ctx.limit)
    )).all()
    return [item(
        category="campaigns", uid=row.id, title=row.title,
        subtitle=f"Proposta de campanha · Estado {row.status}",
        href="/campanhas?proposal=" + row.id, score=row.relevance,
    ) for row in rows]


SearchProvider = Callable[[SearchContext], Awaitable[list[dict]]]
PROVIDERS: dict[str, SearchProvider] = {
    "students": students, "collections": collections, "work": work,
    "views": views, "campaigns": campaigns,
}
ORDER = tuple(PROVIDERS)
