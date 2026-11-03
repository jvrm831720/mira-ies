"""Safe full-snapshot staging and reconciliation for TOTVS RM connectors.

This module is deliberately persistence-agnostic. Callers must persist each
returned run/checkpoint atomically. It does not invent an incremental cursor,
infer deletions from partial extracts, or access an RM endpoint.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping, Sequence


class RMSyncMode(StrEnum):
    FULL_SNAPSHOT = "full_snapshot"
    INCREMENTAL = "incremental"


@dataclass(frozen=True, slots=True)
class RMSourceSyncContract:
    source_name: str
    entity_name: str
    identity_fields: tuple[str, ...]
    coligada_field: str
    supports_full_snapshot: bool
    supports_incremental: bool = False
    incremental_cursor_field: str | None = None
    stable_order_fields: tuple[str, ...] = ()
    deletion_semantics_confirmed: bool = False

    def __post_init__(self) -> None:
        for value, label in (
            (self.source_name, "source_name"),
            (self.entity_name, "entity_name"),
        ):
            if not value.strip() or any(ord(char) < 32 for char in value):
                raise ValueError(f"Contrato RM inválido: {label}.")
        if not self.identity_fields or any(
            not field.strip() or any(ord(char) < 32 for char in field)
            for field in self.identity_fields
        ):
            raise ValueError("O contrato exige campos de identidade estáveis.")
        if len(set(self.identity_fields)) != len(self.identity_fields):
            raise ValueError("Campos de identidade duplicados.")
        if (
            not self.coligada_field.strip()
            or self.coligada_field not in self.identity_fields
        ):
            raise ValueError("Campo da coligada deve integrar a identidade do registro.")
        if self.supports_incremental:
            if not self.incremental_cursor_field:
                raise ValueError("Sync incremental exige cursor homologado.")
            if not self.stable_order_fields:
                raise ValueError("Sync incremental exige ordenação estável homologada.")
        elif self.incremental_cursor_field or self.stable_order_fields:
            raise ValueError("Cursor/ordenação não podem ser declarados sem sync incremental.")


@dataclass(frozen=True, slots=True)
class RMSnapshotScope:
    tenant_id: str
    coligada_id: str
    source_name: str
    entity_name: str
    schema_version: str

    def __post_init__(self) -> None:
        for value in (
            self.tenant_id,
            self.coligada_id,
            self.source_name,
            self.entity_name,
            self.schema_version,
        ):
            if not value.strip() or any(ord(char) < 32 for char in value):
                raise ValueError("Escopo do snapshot incompleto ou inválido.")


@dataclass(frozen=True, slots=True)
class RMStagedPage:
    offset: int
    next_offset: int
    fingerprint: str
    record_count: int
    has_more: bool


@dataclass(frozen=True, slots=True)
class RMSnapshotRun:
    run_id: str
    scope: RMSnapshotScope
    identity_fields: tuple[str, ...]
    coligada_field: str
    pages: tuple[RMStagedPage, ...] = ()
    records: tuple[tuple[str, str], ...] = ()
    next_offset: int = 0
    source_complete: bool = False
    deletion_semantics_confirmed: bool = False
    finalized: bool = False
    record_count: int = 0


@dataclass(frozen=True, slots=True)
class RMCommittedSnapshot:
    run_id: str
    scope: RMSnapshotScope
    identity_fields: tuple[str, ...]
    records: tuple[tuple[str, str], ...]
    record_count: int
    deletion_semantics_confirmed: bool = False


@dataclass(frozen=True, slots=True)
class RMSnapshotDiff:
    added: tuple[str, ...]
    updated: tuple[str, ...]
    unchanged: tuple[str, ...]
    removed: tuple[str, ...]


def _canonical_record(record: Mapping[str, object]) -> str:
    try:
        return json.dumps(
            dict(record),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError):
        raise ValueError("Registro RM deve conter apenas valores JSON válidos.") from None


def _record_identity(
    record: Mapping[str, object], identity_fields: Sequence[str]
) -> str:
    parts: list[str] = []
    for field in identity_fields:
        value = record.get(field)
        if value is None or isinstance(value, bool):
            raise ValueError(f"Identidade RM ausente ou inválida: {field}.")
        normalized = str(value).strip()
        if not normalized or any(ord(char) < 32 for char in normalized):
            raise ValueError(f"Identidade RM ausente ou inválida: {field}.")
        parts.append(normalized)
    return json.dumps(parts, ensure_ascii=False, separators=(",", ":"))


def begin_snapshot_run(
    *,
    run_id: str,
    scope: RMSnapshotScope,
    contract: RMSourceSyncContract,
) -> RMSnapshotRun:
    if not run_id.strip():
        raise ValueError("run_id obrigatório.")
    if not contract.supports_full_snapshot:
        raise ValueError("A origem não homologou extração completa.")
    if (
        scope.source_name != contract.source_name
        or scope.entity_name != contract.entity_name
    ):
        raise ValueError("Escopo não corresponde ao contrato da origem.")
    return RMSnapshotRun(
        run_id=run_id,
        scope=scope,
        identity_fields=contract.identity_fields,
        coligada_field=contract.coligada_field,
        deletion_semantics_confirmed=contract.deletion_semantics_confirmed,
    )


def stage_snapshot_page(
    run: RMSnapshotRun,
    *,
    offset: int,
    next_offset: int,
    records: Sequence[Mapping[str, object]],
    has_more: bool,
) -> RMSnapshotRun:
    """Stage one page; replay of the same offset/content is idempotent."""
    if offset < 0 or next_offset < 0 or next_offset < offset:
        raise ValueError("Offset de paginação inválido.")
    prior = next((page for page in run.pages if page.offset == offset), None)
    if offset != run.next_offset or prior is not None:
        fingerprint = hashlib.sha256(
            json.dumps(
                [_canonical_record(item) for item in records],
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        if (
            prior
            and prior.fingerprint == fingerprint
            and prior.next_offset == next_offset
            and prior.has_more == has_more
        ):
            return run
        raise ValueError("Checkpoint fora de sequência ou replay divergente.")
    if run.finalized or run.source_complete:
        raise ValueError("Não é permitido adicionar páginas a um snapshot concluído.")
    if next_offset - offset != len(records):
        raise ValueError("next_offset deve refletir a quantidade de registros da página.")
    if has_more and next_offset <= offset:
        raise ValueError("Página com continuação deve avançar o offset.")
    if not has_more and records and next_offset == offset:
        raise ValueError("Página final inválida.")

    existing = dict(run.records)
    page_identities: set[str] = set()
    canonical_records: list[str] = []
    for record in records:
        raw_coligada = record.get(run.coligada_field)
        if raw_coligada is None or str(raw_coligada).strip() != run.scope.coligada_id:
            raise ValueError("Registro RM pertence a outra coligada ou não informa a coligada.")
        identity = _record_identity(record, run.identity_fields)
        if identity in page_identities or identity in existing:
            raise ValueError(f"Identidade duplicada no snapshot: {identity}.")
        page_identities.add(identity)
        canonical = _canonical_record(record)
        canonical_records.append(canonical)
        existing[identity] = canonical

    fingerprint = hashlib.sha256(
        json.dumps(
            canonical_records,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    page = RMStagedPage(
        offset=offset,
        next_offset=next_offset,
        fingerprint=fingerprint,
        record_count=len(records),
        has_more=has_more,
    )
    return RMSnapshotRun(
        run_id=run.run_id,
        scope=run.scope,
        identity_fields=run.identity_fields,
        coligada_field=run.coligada_field,
        pages=run.pages + (page,),
        records=tuple(sorted(existing.items())),
        next_offset=next_offset,
        source_complete=not has_more,
        deletion_semantics_confirmed=run.deletion_semantics_confirmed,
        record_count=run.record_count + len(records),
    )


def finalize_snapshot_run(
    run: RMSnapshotRun, *, expected_record_count: int | None = None
) -> RMCommittedSnapshot:
    if run.finalized or not run.source_complete:
        raise ValueError("Snapshot incompleto ou já finalizado.")
    if expected_record_count is not None and expected_record_count != run.record_count:
        raise ValueError("Quantidade extraída diverge do total esperado pela origem.")
    return RMCommittedSnapshot(
        run_id=run.run_id,
        scope=run.scope,
        identity_fields=run.identity_fields,
        records=run.records,
        record_count=run.record_count,
        deletion_semantics_confirmed=run.deletion_semantics_confirmed,
    )


def reconcile_snapshots(
    *,
    previous: RMCommittedSnapshot | None,
    current: RMCommittedSnapshot,
    authoritative_full_snapshot: bool,
) -> RMSnapshotDiff:
    """Compare committed snapshots; removals require an authoritative full extract."""
    current_records = dict(current.records)
    if previous is None:
        return RMSnapshotDiff(
            added=tuple(sorted(current_records)),
            updated=(),
            unchanged=(),
            removed=(),
        )
    if previous.scope != current.scope:
        raise ValueError("Snapshots de tenants, coligadas ou schemas diferentes.")
    if previous.identity_fields != current.identity_fields:
        raise ValueError("Snapshots usam contratos de identidade diferentes.")

    previous_records = dict(previous.records)
    added = sorted(current_records.keys() - previous_records.keys())
    common = current_records.keys() & previous_records.keys()
    updated = sorted(key for key in common if current_records[key] != previous_records[key])
    unchanged = sorted(key for key in common if current_records[key] == previous_records[key])
    removed = (
        sorted(previous_records.keys() - current_records.keys())
        if authoritative_full_snapshot and current.deletion_semantics_confirmed
        else []
    )
    return RMSnapshotDiff(
        added=tuple(added),
        updated=tuple(updated),
        unchanged=tuple(unchanged),
        removed=tuple(removed),
    )
