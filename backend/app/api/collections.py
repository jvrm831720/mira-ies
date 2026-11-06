"""Read-only collections case index backed by verified dispatch obligation facts.

This API does not create agreements, change debts, execute payments or dispatch.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text, bindparam
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthContext, require_permission
from app.db.session import get_db
from app.services.dispatch_core import bind_tenant

from app.services.collection_index_filters import compile_collection_filters
from app.services.object_index_sorting import COLLECTION_SORT_FIELDS, parse_sort_terms

router = APIRouter(prefix="/collections", tags=["Collections"])


def _serialize(row: dict) -> dict:
    return {
        "id": str(row["id"]),
        "external_ref": row["external_ref"],
        "subject_type": row["subject_type"],
        "subject_ref": row["subject_ref"],
        "status": row["status"],
        "balance": str(row["balance"]) if row["balance"] is not None else None,
        "source": row["source"],
        "source_version": row["source_version"],
        "evidence_ref": row["evidence_ref"],
        "verified_at": row["verified_at"].isoformat() if row["verified_at"] else None,
        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
    }


@router.get("/cases")
async def list_collection_cases(
    q: str = Query("", max_length=160),
    status: str | None = Query(None, pattern="^(open|paid|disputed|agreement|cancelled|unknown)$"),
    statuses: str | None = None,
    sort: str = "updated_at",
    sorts: str | None = None,
    filters: str | None = None,
    desc: bool = True,
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    auth: AuthContext = Depends(require_permission("audit.view")),
    db: AsyncSession = Depends(get_db),
):
    """Tenant-scoped, paginated debt facts. Counts cover the filtered result set."""
    await bind_tenant(db, auth.tenant_id)
    where = ["tenant_id=:tenant"]
    params: dict = {"tenant": auth.tenant_id, "limit": limit, "offset": offset}
    if status is not None:
        where.append("status=:status")
        params["status"] = status
    if q.strip():
        # Escape LIKE wildcards so the search cannot accidentally match all rows.
        needle = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        where.append("(external_ref ILIKE :pattern OR subject_ref ILIKE :pattern)")
        params["pattern"] = f"%{needle}%"
    if statuses is not None:
        if len(statuses) > 120:
            raise HTTPException(status_code=422, detail="Filtro de estado extenso.")
        choices = set(statuses.split(",")) if statuses else set()
        valid = {"open", "paid", "disputed", "agreement", "cancelled", "unknown"}
        if not choices or len(choices) > 6 or not choices.issubset(valid):
            raise HTTPException(status_code=422, detail="Estados inválidos.")
        where.append("status IN :statuses")
        params["statuses"] = tuple(choices)
    extra_sql, extra_params, expanding_filter_keys = compile_collection_filters(filters)
    where.extend(extra_sql)
    params.update(extra_params)
    ordering = {"updated_at": "updated_at", "external_ref": "external_ref",
                "status": "status", "balance": "balance", "source": "source"}
    if sort not in ordering:
        raise HTTPException(status_code=422, detail="Ordenação inválida.")
    sort_terms = parse_sort_terms(sorts, COLLECTION_SORT_FIELDS)
    if sort_terms:
        order_clause = ", ".join(
            f"{ordering[field]} {direction.upper()} NULLS LAST"
            for field, direction in sort_terms
        ) + ", id DESC"
    else:
        order_clause = f"{ordering[sort]} {'DESC' if desc else 'ASC'} NULLS LAST, id DESC"
    criteria = " AND ".join(where)
    count_sql = text(f"SELECT count(*) FROM dispatch_obligations WHERE {criteria}")
    for key in (["statuses"] if statuses is not None else []) + expanding_filter_keys:
        count_sql = count_sql.bindparams(bindparam(key, expanding=True))
    count = (await db.execute(
        count_sql, params
    )).scalar_one()
    rows_sql = text(f"""
        SELECT id,external_ref,subject_type,subject_ref,status,balance,source,
               source_version,evidence_ref,verified_at,updated_at
        FROM dispatch_obligations WHERE {criteria}
        ORDER BY {order_clause} LIMIT :limit OFFSET :offset
    """)
    for key in (["statuses"] if statuses is not None else []) + expanding_filter_keys:
        rows_sql = rows_sql.bindparams(bindparam(key, expanding=True))
    rows = (await db.execute(rows_sql, params)).mappings().all()
    return {
        "items": [_serialize(dict(row)) for row in rows],
        "total": count, "offset": offset, "limit": limit,
        "has_more": offset + len(rows) < count,
    }


@router.get("/cases/{case_id}")
async def get_collection_case(
    case_id: str,
    auth: AuthContext = Depends(require_permission("audit.view")),
    db: AsyncSession = Depends(get_db),
):
    """Case facts and verified payment events from the same tenant and obligation."""
    from uuid import UUID

    try:
        case_uuid = str(UUID(case_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Caso não encontrado.") from exc
    await bind_tenant(db, auth.tenant_id)
    row = (await db.execute(text("""
        SELECT id,external_ref,subject_type,subject_ref,status,balance,source,
               source_version,evidence_ref,verified_at,updated_at
        FROM dispatch_obligations WHERE tenant_id=:tenant AND id=:id
    """), {"tenant": auth.tenant_id, "id": case_uuid})).mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Caso não encontrado.")
    events = (await db.execute(text("""
        SELECT id,source,source_event_id,source_version,amount_paid,
               obligation_status,remaining_balance,paid_at
        FROM dispatch_payment_events
        WHERE tenant_id=:tenant AND obligation_ref=:ref
        ORDER BY paid_at DESC,id DESC LIMIT 100
    """), {"tenant": auth.tenant_id, "ref": row["external_ref"]})).mappings().all()
    return {
        "case": _serialize(dict(row)),
        "payment_events": [
            {
                "id": str(e["id"]),
                "source": e["source"],
                "source_event_id": e["source_event_id"],
                "source_version": e["source_version"],
                "amount_paid": str(e["amount_paid"]),
                "obligation_status": e["obligation_status"],
                "remaining_balance": str(e["remaining_balance"]) if e["remaining_balance"] is not None else None,
                "paid_at": e["paid_at"].isoformat() if e["paid_at"] else None,
            }
            for e in events
        ],
        "payment_events_limited": len(events) == 100,
    }
