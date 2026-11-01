"""Endpoints do motor virtual de grupos de alunos (Waves 2.2 e 2.3)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthContext, require_min_role
from app.db.session import get_db
from app.models.student import Student
from app.signals.catalog import SIGNAL_CATALOG
from app.student_groups.catalog import (
    GROUP_CATALOG_VERSION,
    GROUP_DEFINITIONS,
    get_group_definition,
    serialize_catalog_item,
)
from app.student_groups.evaluate import evaluate_student_groups
from app.student_groups.loading import (
    GROUP_BATCH_SIZE,
    GROUP_MAX_STUDENTS,
    iter_student_group_batches,
    student_snapshot,
)
from app.student_groups.pagination import (
    ExpiredGroupCursor,
    InvalidGroupCursor,
    create_group_cursor,
    decode_group_cursor,
)

router = APIRouter(prefix="/student-groups", tags=["Grupos virtuais de alunos"])
_MAX_PAGE_SIZE = 100
_DEFAULT_PAGE_SIZE = 50


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _evaluation_failure() -> HTTPException:
    return HTTPException(
        status_code=503,
        detail="Não foi possível avaliar os grupos neste momento.",
    )


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


async def _build_summary(
    db: AsyncSession,
    *,
    tenant_id: str,
    evaluated_at: datetime,
) -> dict[str, Any]:
    """Single metric path shared by the summary and group-detail endpoints."""
    timestamp = evaluated_at.isoformat()
    try:
        total_eligible = int(
            (
                await db.execute(
                    select(func.count())
                    .select_from(Student)
                    .where(
                        Student.tenant_id == tenant_id,
                        Student.is_active.is_(True),
                    )
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

        async for batch in iter_student_group_batches(db, tenant_id=tenant_id):
            if batch.history_unavailable:
                history_unavailable_batches += 1
            for student in batch.students:
                result = evaluate_student_groups(
                    student_id=student.id,
                    tenant_id=tenant_id,
                    student=student_snapshot(student),
                    assessments=batch.assessments_by_student.get(student.id, []),
                    history_unavailable=batch.history_unavailable,
                    evaluated_at=evaluated_at,
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
        raise _evaluation_failure() from exc

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
                    "percentage": (
                        round(evaluated / total_eligible * 100, 2)
                        if total_eligible
                        else None
                    ),
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
        "evaluated_at": timestamp,
        "scope": "active_students_in_authenticated_tenant",
        "total_eligible": total_eligible,
        "evaluated": evaluated,
        "groups": groups,
        "truncated": truncated,
        "notes": notes,
    }


@router.get("/summary")
async def student_groups_summary(
    auth: AuthContext = Depends(require_min_role("viewer")),
    db: AsyncSession = Depends(get_db),
):
    return await _build_summary(db, tenant_id=auth.tenant_id, evaluated_at=_now())


@router.get("/{group_id}")
async def student_group_detail(
    group_id: str,
    auth: AuthContext = Depends(require_min_role("viewer")),
    db: AsyncSession = Depends(get_db),
):
    definition = get_group_definition(group_id)
    if definition is None:
        raise HTTPException(status_code=404, detail="Grupo não encontrado.")

    summary = await _build_summary(db, tenant_id=auth.tenant_id, evaluated_at=_now())
    aggregate = next(item for item in summary["groups"] if item["id"] == group_id)
    signal_definitions = [SIGNAL_CATALOG[signal_id] for signal_id in definition.signal_ids]
    eligible = summary["total_eligible"]
    return {
        "id": definition.id,
        "name": definition.name,
        "description": definition.description,
        "catalog_version": GROUP_CATALOG_VERSION,
        "signals_used": [
            {
                "id": signal["id"],
                "name": signal["name"],
                "category": signal["category"],
                "description": signal["description"],
                "activation_rule": signal["activation_rule"],
                "data_source": signal["data_source"],
                "reliability": signal["reliability_class"],
                "version": signal["version"],
            }
            for signal in signal_definitions
        ],
        "inclusion_rule": definition.inclusion_rule,
        "metrics": {
            "total_eligible": eligible,
            "total_evaluated": summary["evaluated"],
            "total_belonging": aggregate["matched_count"],
            "total_not_belonging": aggregate["false_count"],
            "total_indeterminate": aggregate["indeterminate_count"],
        },
        "coverage": aggregate["coverage"],
        "limitations": list(definition.limitations),
        "evaluated_at": summary["evaluated_at"],
        "truncated": summary["truncated"],
        "notes": [
            "Este grupo é virtual e pode mudar quando os dados de origem mudarem.",
            "evaluated_at é o instante desta avaliação; não representa a atualização dos dados de origem.",
            *summary["notes"],
        ],
    }


@router.get("/{group_id}/members")
async def student_group_members(
    group_id: str,
    limit: int | None = Query(default=None, ge=1, le=_MAX_PAGE_SIZE),
    cursor: str | None = Query(default=None, max_length=4096),
    auth: AuthContext = Depends(require_min_role("viewer")),
    db: AsyncSession = Depends(get_db),
):
    definition = get_group_definition(group_id)
    if definition is None:
        raise HTTPException(status_code=404, detail="Grupo não encontrado.")

    cursor_payload: dict[str, Any] | None = None
    try:
        if cursor is not None:
            cursor_payload = decode_group_cursor(
                cursor,
                tenant_id=auth.tenant_id,
                group_id=group_id,
            )
            if limit is not None and limit != cursor_payload["limit"]:
                raise InvalidGroupCursor("invalid")
        page_size = limit or (cursor_payload["limit"] if cursor_payload else _DEFAULT_PAGE_SIZE)
    except ExpiredGroupCursor as exc:
        raise HTTPException(status_code=410, detail="Cursor expirado; inicie uma nova consulta.") from exc
    except InvalidGroupCursor as exc:
        raise HTTPException(status_code=400, detail="Cursor inválido para esta consulta.") from exc

    scan_after_id = cursor_payload["after_id"] if cursor_payload else None
    members: list[dict[str, Any]] = []
    scanned = 0
    lookahead_found = False
    member_batch_size = min(GROUP_BATCH_SIZE, max(page_size + 1, 50))
    evaluated_at = _now()

    try:
        async for batch in iter_student_group_batches(
            db,
            tenant_id=auth.tenant_id,
            batch_size=member_batch_size,
            max_students=GROUP_MAX_STUDENTS,
            after_id=scan_after_id,
        ):
            for student in batch.students:
                scanned += 1
                scan_after_id = student.id
                result = evaluate_student_groups(
                    student_id=student.id,
                    tenant_id=auth.tenant_id,
                    student=student_snapshot(student),
                    assessments=batch.assessments_by_student.get(student.id, []),
                    history_unavailable=batch.history_unavailable,
                    evaluated_at=evaluated_at,
                )
                group = next(item for item in result.groups if item.group_id == group_id)
                if group.state != "TRUE":
                    continue
                if len(members) == page_size:
                    lookahead_found = True
                    break
                all_signals = group.signals
                members.append(
                    {
                        "student_id": student.id,
                        "name": student.nome,
                        "group_id": group_id,
                        "membership_status": "TRUE",
                        "matched_signals": [
                            signal for signal in all_signals if signal["status"] == "TRUE"
                        ],
                        "signals": all_signals,
                        "evidence": group.evidence,
                        "limitations": list(group.limitations),
                        "evaluated_at": group.evaluated_at,
                    }
                )
            if lookahead_found:
                break
            if len(batch.students) < member_batch_size:
                break
    except Exception as exc:
        raise _evaluation_failure() from exc

    scan_truncated = scanned >= GROUP_MAX_STUDENTS and not lookahead_found
    has_more: bool | None = True if lookahead_found else (None if scan_truncated else False)
    next_cursor: str | None = None
    if lookahead_found and members:
        # Resume immediately after the last returned member; the lookahead is re-evaluated next time.
        anchor = members[-1]["student_id"]
        next_cursor = create_group_cursor(
            tenant_id=auth.tenant_id,
            group_id=group_id,
            after_id=anchor,
            last_member_id=anchor,
            limit=page_size,
        )
    elif scan_truncated and scan_after_id:
        # The signed checkpoint also records the last returned member, when any, so a capped
        # sparse-group scan can continue without reloading all earlier candidates.
        next_cursor = create_group_cursor(
            tenant_id=auth.tenant_id,
            group_id=group_id,
            after_id=scan_after_id,
            last_member_id=members[-1]["student_id"] if members else None,
            limit=page_size,
        )

    return {
        "group_id": group_id,
        "catalog_version": GROUP_CATALOG_VERSION,
        "evaluated_at": evaluated_at.isoformat(),
        "ordering": "student_id_ascending",
        "count": len(members),
        "members": members,
        "next_cursor": next_cursor,
        "has_more": has_more,
        "truncated": scan_truncated,
        "notes": [
            "Somente alunos com resultado TRUE são listados; FALSE e INDETERMINATE não são membros.",
            "A navegação usa keyset por student_id, com desempate único e estável; não usa OFFSET.",
            "O cursor HMAC é vinculado ao tenant autenticado, group_id, catálogo e limite da página; expira em uma hora.",
            "A avaliação é sob demanda, sem snapshot imutável: alterações nos dados entre páginas podem alterar resultados.",
            "matched_signals contém somente sinais TRUE; signals também mostra os estados FALSE e INDETERMINATE relevantes.",
            *(
                [f"A busca avaliou no máximo {GROUP_MAX_STUDENTS} alunos nesta página; use o cursor para continuar."]
                if scan_truncated
                else []
            ),
        ],
    }
