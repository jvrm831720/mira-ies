"""Composio financial read-only ingestion for MIRA Education.

Reuse the same constrained Composio executor and tenant source policy as Dispatch,
but with a separate finance feature gate and allowlist. No money movement.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.models.composio_connection import TenantComposioAccount, TenantComposioSession
from app.models.financial_composio import StudentFinancialSyncRun
from app.models.student import Student
from app.models.student_services import StudentFinancialReference
from app.services.composio.categories import FINANCE_TOOLKITS
from app.services.composio.connections import _verify_remote_account
from app.services.composio.policy import _tool_schema, _validate_schema_value
from app.services.dispatch_composio_imports import (
    _execute_single_read, _path_parts, _pick, _records,
)
from app.services.dispatch_core import bind_tenant
from app.services.dispatch_sources import require_source, source_tool_is_read_only

class FinancialReadDenied(ValueError):
    """Safe rejection; never include raw financial or authentication payloads."""


def enabled():
    settings = get_settings()
    if not (settings.student_finance_composio_enabled
            and settings.native_academic_services_enabled
            and settings.composio_enabled
            and settings.composio_api_key
            and settings.composio_identity_secret):
        raise FinancialReadDenied("Ingestão financeira Composio está desabilitada.")
    if not settings.student_finance_composio_read_tools.strip():
        raise FinancialReadDenied("Allowlist de leitura financeira não configurada.")


def allowed_tool(tool: str) -> bool:
    allowed = {s.strip().upper() for s in get_settings().student_finance_composio_read_tools.split(",") if s.strip()}
    return tool.upper() in allowed and source_tool_is_read_only(tool)


def parse_amount(raw: Any) -> Decimal:
    if isinstance(raw, bool) or isinstance(raw, (dict, list)) or raw is None:
        raise FinancialReadDenied("Valor financeiro inválido.")
    value = str(raw)
    if not value or len(value) > 24 or not all(c in "0123456789." for c in value):
        raise FinancialReadDenied("Valor exige decimal explícito, sem símbolos ou arredondamento.")
    try:
        amount = Decimal(value)
    except InvalidOperation as exc:
        raise FinancialReadDenied("Valor financeiro inválido.") from exc
    if not amount.is_finite() or amount < 0 or amount > Decimal("9999999999.99") or amount.as_tuple().exponent < -2:
        raise FinancialReadDenied("Precisão ou faixa monetária inválida.")
    return amount


def parse_datetime(raw: Any) -> datetime | None:
    if raw is None or raw == "":
        return None
    if not isinstance(raw, str) or len(raw) > 40:
        raise FinancialReadDenied("Vencimento deve ser ISO 8601 com fuso.")
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise FinancialReadDenied("Vencimento inválido.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise FinancialReadDenied("Vencimento deve incluir fuso horário.")
    return parsed.astimezone(timezone.utc)


def normalize_financial(data: Any, *, rows_path: str, fields: dict[str, str]) -> list[dict[str, Any]]:
    expected = {"external_id", "student_id", "label", "amount", "currency", "status"}
    if set(fields) not in (expected, expected | {"due_at"}):
        raise FinancialReadDenied("Mapeamento financeiro incompleto ou inesperado.")
    for path in (rows_path, *fields.values()):
        _path_parts(path)
    rows = _records(data, rows_path)
    normalized = []
    seen = set()
    for row in rows:
        values = {k: _pick(row, v) for k, v in fields.items()}
        try:
            student_id = str(UUID(str(values["student_id"])))
        except (ValueError, TypeError, AttributeError) as exc:
            raise FinancialReadDenied("Vínculo financeiro exige UUID MIRA explícito.") from exc
        external = values["external_id"]
        label = values["label"]
        status = values["status"]
        if any(not isinstance(v, str) or not v.strip() for v in (external, label, status)):
            raise FinancialReadDenied("Campos identificadores financeiros inválidos.")
        if len(external) > 120 or len(label) > 180 or len(status) > 50 or not external.strip():
            raise FinancialReadDenied("Campos financeiros excedem limites.")
        if external in seen:
            raise FinancialReadDenied("Identificadores repetidos na leitura.")
        seen.add(external)
        if values["currency"] != "BRL":
            raise FinancialReadDenied("Somente valores explicitamente denominados em BRL.")
        normalized.append({
            "external_id": external.strip(), "student_id": student_id,
            "label": label.strip(), "amount": parse_amount(values["amount"]),
            "currency": "BRL", "status": status.strip(),
            "due_at": parse_datetime(values.get("due_at")),
        })
    return normalized


async def sync_financial(
    db: AsyncSession, *, tenant_id: str, actor_id: str,
    account_id: str, tool_slug: str, arguments: dict[str, Any],
    rows_path: str, fields: dict[str, str], idempotency_key: str,
) -> dict[str, Any]:
    enabled()
    tool = tool_slug.strip().upper()
    if not allowed_tool(tool):
        raise FinancialReadDenied("Ferramenta não autorizada para leitura financeira.")
    if len(idempotency_key) < 16 or len(idempotency_key) > 120:
        raise FinancialReadDenied("Chave idempotente inválida.")
    if not isinstance(arguments, dict) or len(json.dumps(arguments, allow_nan=False)) > 16000:
        raise FinancialReadDenied("Argumentos da ferramenta inválidos.")
    await bind_tenant(db, tenant_id)
    state = await require_source(db, tenant_id=tenant_id, kind="composio", reference=account_id, tool_slug=tool)
    if not state.available:
        raise FinancialReadDenied("Conta Composio ou política não autorizada.")
    account = (await db.execute(select(TenantComposioAccount).where(
        TenantComposioAccount.tenant_id == tenant_id,
        TenantComposioAccount.connected_account_id == account_id,
        TenantComposioAccount.status == "active",
        TenantComposioAccount.disconnected_at.is_(None),
    ))).scalar_one_or_none()
    if account is None or account.toolkit_slug not in FINANCE_TOOLKITS:
        raise FinancialReadDenied("A conta deve pertencer a um toolkit financeiro aprovado.")
    identity = (await db.execute(select(TenantComposioSession).where(
        TenantComposioSession.tenant_id == tenant_id,
        TenantComposioSession.status == "active",
    ))).scalar_one_or_none()
    if identity is None:
        raise FinancialReadDenied("Identidade Composio ativa não encontrada.")

    # Refuse stale or reassigned connected accounts before remote execution.
    await run_in_threadpool(
        _verify_remote_account,
        connected_account_id=account_id, expected_user_id=identity.composio_user_id,
        expected_toolkit=account.toolkit_slug,
    )
    schema = await run_in_threadpool(_tool_schema, account.toolkit_slug, tool)
    _validate_schema_value(arguments, schema)
    for value in (rows_path, *fields.values()):
        _path_parts(value)
    request_hash = hashlib.sha256(json.dumps({
        "account": account_id, "tool": tool, "arguments": arguments,
        "rows_path": rows_path, "fields": fields,
    }, sort_keys=True, allow_nan=False).encode()).hexdigest()
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:value,0))"),
                     {"value": f"student-finance:{tenant_id}:{idempotency_key}"})
    previous = (await db.execute(select(StudentFinancialSyncRun).where(
        StudentFinancialSyncRun.tenant_id == tenant_id,
        StudentFinancialSyncRun.idempotency_key == idempotency_key,
    ))).scalar_one_or_none()
    if previous is not None:
        if previous.request_hash != request_hash:
            raise FinancialReadDenied("Idempotency-Key vinculada a outra consulta.")
        return {"status": "synced", "count": previous.record_count,
                "deduplicated": True, "run_id": previous.id}
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:value,0))"),
                     {"value": f"student-finance:quota:{tenant_id}"})
    recent = (await db.execute(select(StudentFinancialSyncRun.id).where(
        StudentFinancialSyncRun.tenant_id == tenant_id,
        StudentFinancialSyncRun.synced_at >= datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0),
    ))).scalars().all()
    if len(recent) >= 30:
        raise FinancialReadDenied("Limite de consultas financeiras atingido.")
    data = await run_in_threadpool(
        _execute_single_read, user_id=identity.composio_user_id,
        account_id=account_id, toolkit=account.toolkit_slug,
        tool_slug=tool, arguments=arguments,
    )
    normalized = normalize_financial(data, rows_path=rows_path, fields=fields)
    ids = {row["student_id"] for row in normalized}
    if ids:
        known = set((await db.execute(select(Student.id).where(
            Student.tenant_id == tenant_id, Student.id.in_(ids), Student.is_active.is_(True),
        ))).scalars().all())
        if ids != known:
            raise FinancialReadDenied("Alunos sem vínculo ativo na mesma instituição.")
    now = datetime.now(timezone.utc)
    # Derived source key prevents different accounts/tools from overwriting one another.
    source = "composio_" + hashlib.sha256((account_id + ":" + tool).encode()).hexdigest()[:22]
    for row in normalized:
        stmt = pg_insert(StudentFinancialReference).values(
            tenant_id=tenant_id, student_id=row["student_id"], source=source,
            external_id=row["external_id"], label=row["label"], amount=row["amount"],
            currency="BRL", due_on=row["due_at"], source_status=row["status"], observed_at=now,
        ).on_conflict_do_update(
            constraint="uq_mira_financial_reference_source",
            set_={"label": row["label"], "amount": row["amount"], "currency": "BRL",
                  "due_on": row["due_at"], "source_status": row["status"], "observed_at": now},
        )
        await db.execute(stmt)
    audit = StudentFinancialSyncRun(
        tenant_id=tenant_id, actor_id=actor_id, connected_account_id=account_id,
        toolkit=account.toolkit_slug, tool_slug=tool,
        request_hash=request_hash, idempotency_key=idempotency_key,
        record_count=len(normalized), synced_at=now,
    )
    db.add(audit)
    await db.commit()
    return {"status": "synced", "count": len(normalized), "deduplicated": False,
            "run_id": audit.id, "payment_enabled": False, "reconciled": False}
