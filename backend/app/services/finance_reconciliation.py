"""Metadata-driven financial reconciliation: many workspace sources, no untrusted code.

Profiles configure mapping, aliases/status transitions and explicit student links.
The financial state is always a source-reported observation, never a verified
payment or authority to create charges. All persistence is tenant-scoped.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from difflib import SequenceMatcher
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.models.composio_connection import TenantComposioAccount, TenantComposioSession
from app.models.finance_reconciliation import (
    FinanceSourceProfile, FinanceStudentLink, FinanceIngestionBatch,
    FinanceObservation, FinanceReviewCase, FinanceReviewEvent,
)
from app.models.student import Student
from app.models.student_services import StudentFinancialReference
from app.services.composio.categories import FINANCE_TOOLKITS
from app.services.composio.connections import _verify_remote_account
from app.services.composio.policy import _tool_schema, _validate_schema_value
from app.services.dispatch_composio_imports import _execute_single_read, _records, _pick
from app.services.dispatch_core import bind_tenant
from app.services.dispatch_sources import require_source
from app.services import student_finance_composio as composio

REQUIRED = {"external_id", "student_reference", "amount", "currency", "status"}
OPTIONAL = {"label", "due_at", "paid_amount", "correlation_key", "source_updated_at"}
STATES = {"open", "overdue", "partially_paid", "reported_paid", "cancelled", "disputed", "unknown"}
_ID = re.compile(r"^[a-z][a-z0-9_]{0,23}$")
_SENSITIVE = re.compile(
    r"password|token|secret|credential|api_?key|private_?key|authorization|bank_?account|iban|routing_?number", re.I,
)
DEFAULT_WORKFLOW = {
    "transitions": {
        "open": ["triage"],
        "triage": ["awaiting_source", "reviewed"],
        "awaiting_source": ["triage"],
        "reviewed": [],
    },
    "labels": {
        "open": "Pendente",
        "triage": "Em análise",
        "awaiting_source": "Aguardando fonte",
        "reviewed": "Revisado (não comprova quitação)",
    },
}
ALIASES = {
    "external_id": ["id", "id do titulo", "numero boleto", "parcela", "id fatura"],
    "student_reference": ["matricula", "aluno", "codigo aluno", "student id", "estudante"],
    "label": ["descricao", "mensalidade", "referencia", "description"],
    "amount": ["valor", "valor total", "amount", "total", "cobranca"],
    "paid_amount": ["valor pago", "pago parcial", "paid amount"],
    "currency": ["moeda", "currency"],
    "status": ["situacao", "status financeiro", "status boleto", "situacao pagamento"],
    "due_at": ["vencimento", "data vencimento", "due date"],
    "correlation_key": ["identificador contrato", "numero contrato", "obrigacao"],
    "source_updated_at": ["atualizado em", "data atualizacao", "updated at"],
}


class ReconciliationDenied(ValueError):
    """Do not expose provider contents or raw authentication in error messages."""


def require_enabled() -> None:
    s = get_settings()
    if not (s.student_finance_reconciliation_enabled
            and s.native_academic_enabled and s.native_academic_services_enabled):
        raise ReconciliationDenied("Conciliação financeira por metadados em homologação.")


def validate_workflow(raw: Any) -> dict[str, Any]:
    data = raw if raw is not None else DEFAULT_WORKFLOW
    if not isinstance(data, dict) or set(data) != {"transitions", "labels"}:
        raise ReconciliationDenied("Workflow deve descrever transições e rótulos.")
    transitions, labels = data["transitions"], data["labels"]
    if not isinstance(transitions, dict) or not isinstance(labels, dict):
        raise ReconciliationDenied("Estrutura de workflow inválida.")
    states = set(transitions)
    if not 2 <= len(states) <= 8 or "open" not in states:
        raise ReconciliationDenied("Workflow exige estado inicial e até oito etapas.")
    if any(not isinstance(k, str) or not _ID.fullmatch(k) for k in states):
        raise ReconciliationDenied("Identificador de etapa inválido.")
    if set(labels) != states or any(
        not isinstance(v, str) or not 1 <= len(v.strip()) <= 65 for v in labels.values()
    ):
        raise ReconciliationDenied("Rótulos obrigatórios para todas as etapas.")
    for state, next_states in transitions.items():
        if (not isinstance(next_states, list) or len(next_states) > 8
                or len(set(next_states)) != len(next_states)
                or any(n not in states or n == state or n == "open" for n in next_states)):
            raise ReconciliationDenied("Transições configuradas são inválidas.")
    # Workflow only controls human review. It never sets a financial state.
    return {"transitions": {k: list(v) for k, v in transitions.items()},
            "labels": dict(labels)}


def validate_profile(
    *, name: str, source_kind: str, field_map: dict[str, str],
    status_map: dict[str, str], rows_path: str, student_lookup: str,
    connected_account_id: str | None, tool_slug: str | None, workflow: dict | None,
) -> dict[str, Any]:
    if not isinstance(name, str) or not 3 <= len(name.strip()) <= 100:
        raise ReconciliationDenied("Nome da origem inválido.")
    if source_kind not in {"composio", "import"}:
        raise ReconciliationDenied("A origem deve ser Composio ou arquivo importado.")
    if student_lookup not in {"mira_id", "verified_external"}:
        raise ReconciliationDenied("Vínculo com aluno deve ser explícito e verificável.")
    if not isinstance(field_map, dict) or not REQUIRED <= set(field_map) <= REQUIRED | OPTIONAL:
        raise ReconciliationDenied("Mapeamento canônico incompleto ou contém campos extras.")
    if len(set(field_map.values())) != len(field_map):
        raise ReconciliationDenied("Um campo de origem não pode alimentar dois campos canônicos.")
    for value in field_map.values():
        if not isinstance(value, str) or not value.strip() or len(value) > 120:
            raise ReconciliationDenied("Nome de coluna ou caminho inválido.")
        if _SENSITIVE.search(value):
            raise ReconciliationDenied("Mapeamento de campos sigilosos é proibido.")
        if source_kind == "composio":
            composio.safe_mapping_path(value)
        elif any(ord(c) < 32 for c in value) or value.startswith((".", "_")):
            raise ReconciliationDenied("Coluna de importação inválida.")
    if not isinstance(rows_path, str) or len(rows_path) > 240:
        raise ReconciliationDenied("Caminho de registros inválido.")
    if source_kind == "composio":
        composio.safe_mapping_path(rows_path)
        if not isinstance(connected_account_id, str) or not connected_account_id.strip():
            raise ReconciliationDenied("Perfil Composio exige uma conta conectada.")
        if not isinstance(tool_slug, str) or not composio.allowed_tool(tool_slug):
            raise ReconciliationDenied("Ferramenta financeira não permitida para leitura.")
    elif connected_account_id or tool_slug or rows_path:
        raise ReconciliationDenied("Perfil de planilha não executa ferramentas externas.")
    if not isinstance(status_map, dict) or len(status_map) > 40:
        raise ReconciliationDenied("Mapa de situações inválido.")
    normalized_status = {}
    for raw, state in status_map.items():
        if not isinstance(raw, str) or not 1 <= len(raw.strip()) <= 50 or state not in STATES:
            raise ReconciliationDenied("Estado financeiro fora dos valores canônicos.")
        key = raw.strip().casefold()
        if key in normalized_status:
            raise ReconciliationDenied("Estado de origem duplicado.")
        normalized_status[key] = state
    return {
        "name": name.strip(), "source_kind": source_kind,
        "connected_account_id": connected_account_id.strip() if connected_account_id else None,
        "tool_slug": tool_slug.strip().upper() if tool_slug else None,
        "rows_path": rows_path.strip(), "field_map": dict(field_map),
        "status_map": normalized_status, "review_workflow": validate_workflow(workflow),
        "student_lookup": student_lookup,
    }


def _value(row: dict, field: str, profile: FinanceSourceProfile) -> Any:
    path = profile.field_map.get(field)
    if path is None:
        return None
    if profile.source_kind == "import":
        if path not in row:
            raise ReconciliationDenied("A planilha não contém uma coluna mapeada.")
        return row[path]
    try:
        return _pick(row, path)
    except (ValueError, KeyError, TypeError) as exc:
        raise ReconciliationDenied("Resposta Composio sem um campo mapeado.") from exc


def _small(raw: Any, size: int, *, required: bool = True) -> str | None:
    if raw is None or raw == "":
        if required:
            raise ReconciliationDenied("Campo financeiro obrigatório ausente.")
        return None
    if not isinstance(raw, (str, int)) or isinstance(raw, bool):
        raise ReconciliationDenied("Campo financeiro deve ser um escalar.")
    value = str(raw).strip()
    if not value and required:
        raise ReconciliationDenied("Campo financeiro obrigatório vazio.")
    if len(value) > size or any(ord(ch) < 32 for ch in value):
        raise ReconciliationDenied("Campo financeiro maior que o permitido.")
    return value or None


def normalize_rows(rows: Any, profile: FinanceSourceProfile) -> list[dict[str, Any]]:
    if not isinstance(rows, list) or not 1 <= len(rows) <= 100:
        raise ReconciliationDenied("Cada lote requer de 1 a 100 registros.")
    if len(json.dumps(rows, default=str, ensure_ascii=False)) > 256 * 1024:
        raise ReconciliationDenied("Lote acima do limite de 256 KB.")
    if any(not isinstance(row, dict) or len(row) > 48 for row in rows):
        raise ReconciliationDenied("Registros devem ser objetos de até 48 campos.")
    output = []
    seen = set()
    for row in rows:
        external = _small(_value(row, "external_id", profile), 120)
        if external in seen:
            raise ReconciliationDenied("Duplicidade de obrigação dentro do lote.")
        seen.add(external)
        student_ref = _small(_value(row, "student_reference", profile), 120)
        if profile.student_lookup == "mira_id":
            try:
                student_ref = str(UUID(student_ref))
            except ValueError as exc:
                raise ReconciliationDenied("UUID de aluno inválido, sem correspondência por nome.") from exc
        currency = _small(_value(row, "currency", profile), 3)
        if currency != "BRL":
            raise ReconciliationDenied("Moeda diferente de BRL requer homologação.")
        try:
            amount = composio.parse_amount(_value(row, "amount", profile))
            paid_raw = _value(row, "paid_amount", profile)
            paid = composio.parse_amount(paid_raw) if paid_raw is not None and paid_raw != "" else Decimal("0.00")
            due_at = composio.parse_datetime(_value(row, "due_at", profile))
            source_updated_at = composio.parse_datetime(_value(row, "source_updated_at", profile))
        except (ValueError, TypeError) as exc:
            raise ReconciliationDenied("Valor monetário ou data de origem inválida.") from exc
        if paid > amount:
            raise ReconciliationDenied("Pagamento informado excede o valor total da obrigação.")
        raw_status = _small(_value(row, "status", profile), 50)
        state = profile.status_map.get(raw_status.casefold(), "unknown")
        label = _small(_value(row, "label", profile), 180, required=False) or "Obrigação financeira"
        correlation = _small(_value(row, "correlation_key", profile), 120, required=False)
        output.append({
            "external_id": external, "student_ref": student_ref, "label": label,
            "amount": amount, "paid_amount": paid, "currency": currency,
            "due_at": due_at, "source_updated_at": source_updated_at,
            "raw_status": raw_status, "canonical_state": state,
            "correlation_key": correlation,
        })
    return output


def _fingerprint(row: dict[str, Any]) -> str:
    data = {k: (v.isoformat() if isinstance(v, datetime) else str(v) if isinstance(v, Decimal) else v)
            for k, v in row.items()}
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
    ).hexdigest()


def _digest(data: Any) -> str:
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, ensure_ascii=False, default=str, allow_nan=False).encode()
    ).hexdigest()


def suggest_columns(headers: list[str]) -> dict[str, dict[str, Any]]:
    if len(headers) > 48:
        raise ReconciliationDenied("Cabeçalhos além do limite.")
    def plain(raw: str) -> str:
        value = unicodedata.normalize("NFKD", str(raw))
        value = "".join(ch for ch in value if not unicodedata.combining(ch))
        return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()
    output = {}
    for field, aliases in ALIASES.items():
        candidates = [
            (max(SequenceMatcher(None, plain(h), plain(a)).ratio() for a in [field, *aliases]), h)
            for h in headers if isinstance(h, str) and h and len(h) <= 120
        ]
        if candidates:
            score, proposed = max(candidates)
            if score >= 0.55:
                output[field] = {"suggested_header": proposed, "confidence": round(score, 2),
                                 "requires_confirmation": True}
    return output


async def get_profile(db: AsyncSession, tenant_id: str, profile_id: str, *, lock: bool = False):
    await bind_tenant(db, tenant_id)
    statement = select(FinanceSourceProfile).where(
        FinanceSourceProfile.tenant_id == tenant_id, FinanceSourceProfile.id == profile_id,
    )
    if lock:
        statement = statement.with_for_update()
    row = (await db.execute(statement)).scalar_one_or_none()
    if row is None:
        raise ReconciliationDenied("Perfil financeiro não encontrado neste workspace.")
    return row


async def _resolve_students(db: AsyncSession, profile: FinanceSourceProfile, rows: list[dict[str, Any]]):
    ids = {x["student_ref"] for x in rows}
    if profile.student_lookup == "verified_external":
        links = (await db.execute(select(FinanceStudentLink).where(
            FinanceStudentLink.tenant_id == profile.tenant_id,
            FinanceStudentLink.profile_id == profile.id,
            FinanceStudentLink.external_student_ref.in_(ids),
        ))).scalars().all()
        found = {row.external_student_ref: row.student_id for row in links}
        if set(found) != ids:
            raise ReconciliationDenied("Há identificadores externos sem vínculo verificado com aluno MIRA.")
    else:
        found = {item: item for item in ids}
    actual = {str(row) for row in (await db.execute(select(Student.id).where(
        Student.tenant_id == profile.tenant_id,
        Student.id.in_(set(found.values())),
        Student.is_active.is_(True),
    ))).scalars().all()}
    if actual != set(found.values()):
        raise ReconciliationDenied("Há alunos inativos ou de outro workspace nos registros.")
    return found


async def ingest_rows(
    db: AsyncSession, *, tenant_id: str, profile: FinanceSourceProfile,
    actor_id: str, rows: Any, idempotency_key: str, origin: str,
    request_digest: str | None = None,
) -> dict[str, Any]:
    require_enabled()
    if not profile.enabled or profile.tenant_id != tenant_id or origin != profile.source_kind:
        raise ReconciliationDenied("Origem financeira não habilitada para este workspace.")
    if not isinstance(idempotency_key, str) or not 16 <= len(idempotency_key) <= 120:
        raise ReconciliationDenied("Idempotency-Key inválida.")
    await bind_tenant(db, tenant_id)
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:lock,0))"),
                     {"lock": f"finance:profile:{tenant_id}:{profile.id}"})
    # Only canonical mapped values enter observations; never raw Composio payloads.
    canonical = normalize_rows(rows, profile)
    digest = request_digest or _digest({"version": profile.mapping_version, "rows": canonical})
    previous = (await db.execute(select(FinanceIngestionBatch).where(
        FinanceIngestionBatch.tenant_id == tenant_id,
        FinanceIngestionBatch.profile_id == profile.id,
        FinanceIngestionBatch.idempotency_key == idempotency_key,
    ))).scalar_one_or_none()
    if previous:
        if previous.payload_digest != digest:
            raise ReconciliationDenied("Chave idempotente já usada com conteúdo diferente.")
        return {"batch_id": previous.id, "imported": previous.imported_count,
                "unchanged": previous.unchanged_count, "deduplicated": True,
                "settlement_confirmed": False}
    students = await _resolve_students(db, profile, canonical)
    source_key = "profile_" + profile.id
    pending = []
    unchanged = 0
    # Resolve every conflict BEFORE creating the immutable batch audit record.
    for entry in canonical:
        student_id = students[entry["student_ref"]]
        recorded = {**entry, "student_id": student_id}
        fingerprint = _fingerprint(recorded)
        prior = (await db.execute(select(FinanceObservation).where(
            FinanceObservation.tenant_id == tenant_id,
            FinanceObservation.profile_id == profile.id,
            FinanceObservation.external_id == entry["external_id"],
        ).order_by(FinanceObservation.observed_at.desc(), FinanceObservation.id.desc()).limit(1))).scalar_one_or_none()
        if prior and prior.student_id != student_id:
            raise ReconciliationDenied("Obrigação já vinculada a outro aluno; é necessária revisão de vínculo.")
        if prior and prior.source_updated_at:
            if entry["source_updated_at"] is None or entry["source_updated_at"] < prior.source_updated_at:
                raise ReconciliationDenied("Atualização de origem ausente ou anterior ao registro persistido.")
            if entry["source_updated_at"] == prior.source_updated_at and prior.fingerprint != fingerprint:
                raise ReconciliationDenied("A fonte alterou dados sem avançar a versão temporal.")
        already = (await db.execute(select(FinanceObservation.id).where(
            FinanceObservation.tenant_id == tenant_id, FinanceObservation.profile_id == profile.id,
            FinanceObservation.fingerprint == fingerprint,
        ))).scalar_one_or_none()
        if already is not None:
            unchanged += 1
            continue
        current = (await db.execute(select(StudentFinancialReference).where(
            StudentFinancialReference.tenant_id == tenant_id,
            StudentFinancialReference.source == source_key,
            StudentFinancialReference.external_id == entry["external_id"],
        ))).scalar_one_or_none()
        if current and current.student_id != student_id:
            raise ReconciliationDenied("Fonte duplicou uma obrigação em dois alunos.")
        pending.append((entry, student_id, fingerprint))
    imported = len(pending)
    batch = FinanceIngestionBatch(
        tenant_id=tenant_id, profile_id=profile.id, actor_id=actor_id, origin=origin,
        idempotency_key=idempotency_key, payload_digest=digest,
        mapping_version=profile.mapping_version, row_count=len(canonical),
        imported_count=imported, unchanged_count=unchanged,
    )
    db.add(batch)
    await db.flush()
    # Snapshot per profile; entries from distinct accounts never overwrite each other.
    for entry, student_id, fingerprint in pending:
        db.add(FinanceObservation(
            tenant_id=tenant_id, profile_id=profile.id, student_id=student_id,
            batch_id=batch.id, external_id=entry["external_id"],
            correlation_key=entry["correlation_key"], fingerprint=fingerprint,
            label=entry["label"], amount=entry["amount"], paid_amount=entry["paid_amount"],
            currency="BRL", due_at=entry["due_at"],
            source_updated_at=entry["source_updated_at"],
            canonical_state=entry["canonical_state"], raw_status=entry["raw_status"],
            mapping_version=profile.mapping_version,
        ))
        statement = pg_insert(StudentFinancialReference).values(
            tenant_id=tenant_id, student_id=student_id, source=source_key,
            external_id=entry["external_id"], label=entry["label"],
            amount=entry["amount"], currency="BRL", due_on=entry["due_at"],
            source_status=entry["canonical_state"], observed_at=datetime.now(timezone.utc),
        ).on_conflict_do_update(
            constraint="uq_mira_financial_reference_source",
            set_={
                "label": entry["label"], "amount": entry["amount"], "currency": "BRL",
                "due_on": entry["due_at"], "source_status": entry["canonical_state"],
                "observed_at": datetime.now(timezone.utc),
            },
        )
        await db.execute(statement)
    await db.commit()
    return {"batch_id": batch.id, "imported": imported, "unchanged": unchanged,
            "deduplicated": False, "settlement_confirmed": False,
            "warning": "Fonte relata estados; nenhuma liquidação foi confirmada."}


async def preview_rows(db: AsyncSession, *, profile: FinanceSourceProfile, rows: Any) -> dict[str, Any]:
    require_enabled()
    await bind_tenant(db, profile.tenant_id)
    canonical = normalize_rows(rows, profile)
    try:
        await _resolve_students(db, profile, canonical)
        linked = True
    except ReconciliationDenied:
        linked = False
    return {
        "total": len(canonical), "students_linked": linked,
        "states": {state: sum(x["canonical_state"] == state for x in canonical) for state in STATES},
        "requires_confirmation": True, "persisted": False, "settlement_confirmed": False,
        "mapping_version": profile.mapping_version,
    }


async def sync_composio_profile(
    db: AsyncSession, *, tenant_id: str, profile_id: str, actor_id: str,
    arguments: dict[str, Any], idempotency_key: str,
) -> dict[str, Any]:
    require_enabled()
    composio.enabled()
    profile = await get_profile(db, tenant_id, profile_id, lock=True)
    if not profile.enabled or profile.source_kind != "composio":
        raise ReconciliationDenied("Perfil Composio não habilitado.")
    if not composio.allowed_tool(profile.tool_slug):
        raise ReconciliationDenied("Ferramenta fora da allowlist financeira.")
    if not isinstance(arguments, dict) or len(json.dumps(arguments, allow_nan=False)) > 16000:
        raise ReconciliationDenied("Argumentos Composio inválidos.")
    digest = _digest({"profile": profile.id, "version": profile.mapping_version, "arguments": arguments})
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:lock,0))"),
                     {"lock": f"finance:profile:{tenant_id}:{profile.id}"})
    prior = (await db.execute(select(FinanceIngestionBatch).where(
        FinanceIngestionBatch.tenant_id == tenant_id, FinanceIngestionBatch.profile_id == profile.id,
        FinanceIngestionBatch.idempotency_key == idempotency_key,
    ))).scalar_one_or_none()
    if prior is not None:
        if prior.payload_digest != digest:
            raise ReconciliationDenied("Idempotency-Key usada para outra solicitação.")
        return {"batch_id": prior.id, "imported": prior.imported_count,
                "unchanged": prior.unchanged_count, "deduplicated": True,
                "settlement_confirmed": False}
    recent = (await db.execute(select(FinanceIngestionBatch.id).where(
        FinanceIngestionBatch.tenant_id == tenant_id,
        FinanceIngestionBatch.origin == "composio",
        FinanceIngestionBatch.received_at >= datetime.now(timezone.utc) - timedelta(hours=1),
    ).limit(30))).scalars().all()
    if len(recent) >= 30:
        raise ReconciliationDenied("Cota horária de 30 leituras Composio atingida.")
    authorized = await require_source(db, tenant_id=tenant_id, kind="composio",
                                      reference=profile.connected_account_id, tool_slug=profile.tool_slug)
    if not authorized.available:
        raise ReconciliationDenied("Conta Composio não autorizada para este workspace.")
    account = (await db.execute(select(TenantComposioAccount).where(
        TenantComposioAccount.tenant_id == tenant_id,
        TenantComposioAccount.connected_account_id == profile.connected_account_id,
        TenantComposioAccount.status == "active",
        TenantComposioAccount.disconnected_at.is_(None),
    ))).scalar_one_or_none()
    if account is None or account.toolkit_slug not in FINANCE_TOOLKITS:
        raise ReconciliationDenied("Conta não é uma integração financeira habilitada.")
    identity = (await db.execute(select(TenantComposioSession).where(
        TenantComposioSession.tenant_id == tenant_id, TenantComposioSession.status == "active",
    ))).scalar_one_or_none()
    if identity is None:
        raise ReconciliationDenied("Sessão Composio do workspace indisponível.")
    await run_in_threadpool(
        _verify_remote_account, connected_account_id=profile.connected_account_id,
        expected_user_id=identity.composio_user_id, expected_toolkit=account.toolkit_slug,
    )
    schema = await run_in_threadpool(_tool_schema, account.toolkit_slug, profile.tool_slug)
    _validate_schema_value(arguments, schema)
    result = await run_in_threadpool(
        _execute_single_read, user_id=identity.composio_user_id,
        account_id=profile.connected_account_id, toolkit=account.toolkit_slug,
        tool_slug=profile.tool_slug, arguments=arguments,
    )
    rows = _records(result, profile.rows_path)
    if not rows:
        # An empty result must not erase existing obligations.
        raise ReconciliationDenied("Fonte retornou lote vazio; nenhum registro anterior foi modificado.")
    return await ingest_rows(
        db, tenant_id=tenant_id, profile=profile, actor_id=actor_id,
        rows=rows, idempotency_key=idempotency_key, origin="composio",
        request_digest=digest,
    )


async def list_reconciliation(db: AsyncSession, tenant_id: str, limit: int = 50) -> dict[str, Any]:
    require_enabled()
    await bind_tenant(db, tenant_id)
    # Latest observations only. Correlation is explicit; never infer equivalence
    # between two systems from student name, invoice number or matching amount.
    observations = (await db.execute(select(FinanceObservation).where(
        FinanceObservation.tenant_id == tenant_id,
        FinanceObservation.correlation_key.is_not(None),
    ).order_by(FinanceObservation.observed_at.desc(), FinanceObservation.id.desc()).limit(1000))).scalars().all()
    latest = {}
    for obs in observations:
        latest.setdefault((obs.profile_id, obs.external_id), obs)
    groups = {}
    for obs in latest.values():
        if obs.correlation_key:
            groups.setdefault((obs.student_id, obs.correlation_key), []).append(obs)
    report = []
    for (student_id, correlation), entries in groups.items():
        sources = {x.profile_id for x in entries}
        disagreement = len({(str(x.amount), x.canonical_state, str(x.paid_amount)) for x in entries}) > 1
        report.append({
            "student_id": student_id, "correlation_key": correlation,
            "sources": len(sources), "observations": len(entries),
            "result": "conflict" if disagreement and len(sources) > 1 else (
                "multi_source_consistent" if len(sources) > 1 else "single_source"
            ),
            "settlement_confirmed": False,
        })
    report.sort(key=lambda x: (x["result"] != "conflict", x["student_id"], x["correlation_key"]))
    return {"items": report[:limit], "total_groups_examined": len(report),
            "scope": "latest_1000_observations", "automatic_settlement": False}
