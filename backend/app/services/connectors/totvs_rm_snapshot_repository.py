"""Transactional PostgreSQL repository for TOTVS RM snapshot synchronization.

All write methods own one database transaction and set the tenant RLS context
(app.tenant_id) locally before reading or writing tenant-scoped rows.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rm_sync import RmSyncPage, RmSyncRecord, RmSyncRun, RmSyncScope
from app.services.connectors.totvs_rm_snapshot_sync import (
    RMCommittedSnapshot,
    RMSourceSyncContract,
    RMSnapshotRun,
    RMSnapshotScope,
    RMStagedPage,
    begin_snapshot_run,
    finalize_snapshot_run,
    reconcile_snapshots,
    stage_snapshot_page,
)


def _canonical(payload: dict) -> str:
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RMSnapshotConflict(RuntimeError):
    """A conflicting or invalid persisted snapshot transition."""


class RMPostgresSnapshotRepository:
    """Tenant-scoped, restart-safe persistence for snapshot runs."""

    async def _set_tenant_context(self, session: AsyncSession, tenant_id: str) -> None:
        await session.execute(
            text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
            {"tenant_id": tenant_id},
        )

    async def begin_run(
        self,
        session: AsyncSession,
        *,
        run_id: str,
        scope: RMSnapshotScope,
        contract: RMSourceSyncContract,
    ) -> str:
        validated = begin_snapshot_run(run_id=run_id, scope=scope, contract=contract)
        async with session.begin():
            await self._set_tenant_context(session, scope.tenant_id)
            await session.execute(
                pg_insert(RmSyncScope)
                .values(
                    id=str(uuid4()),
                    tenant_id=scope.tenant_id,
                    coligada_id=scope.coligada_id,
                    source_name=scope.source_name,
                    entity_name=scope.entity_name,
                    schema_version=scope.schema_version,
                )
                .on_conflict_do_nothing(
                    index_elements=[
                        "tenant_id", "coligada_id", "source_name", "entity_name", "schema_version"
                    ]
                )
            )
            scope_row = (
                await session.execute(
                    select(RmSyncScope)
                    .where(
                        RmSyncScope.tenant_id == scope.tenant_id,
                        RmSyncScope.coligada_id == scope.coligada_id,
                        RmSyncScope.source_name == scope.source_name,
                        RmSyncScope.entity_name == scope.entity_name,
                        RmSyncScope.schema_version == scope.schema_version,
                    )
                    .with_for_update()
                )
            ).scalar_one()

            existing_id = await session.get(RmSyncRun, run_id)
            if existing_id:
                if (
                    existing_id.tenant_id == scope.tenant_id
                    and existing_id.scope_id == scope_row.id
                    and existing_id.status == "staging"
                ):
                    return run_id
                raise RMSnapshotConflict("run_id já existe e não pode ser reutilizado.")
            active = (
                await session.execute(
                    select(RmSyncRun.id).where(
                        RmSyncRun.scope_id == scope_row.id,
                        RmSyncRun.tenant_id == scope.tenant_id,
                        RmSyncRun.status == "staging",
                    ).with_for_update()
                )
            ).scalar_one_or_none()
            if active:
                raise RMSnapshotConflict("Já existe uma execução em staging para este escopo.")

            session.add(
                RmSyncRun(
                    id=validated.run_id,
                    scope_id=scope_row.id,
                    tenant_id=scope.tenant_id,
                    identity_fields=list(validated.identity_fields),
                    coligada_field=validated.coligada_field,
                    deletion_semantics_confirmed=validated.deletion_semantics_confirmed,
                    status="staging",
                )
            )
            await session.flush()
        return run_id

    async def stage_page(
        self,
        session: AsyncSession,
        *,
        tenant_id: str,
        run_id: str,
        offset: int,
        next_offset: int,
        records: list[dict],
        has_more: bool,
    ) -> int:
        async with session.begin():
            await self._set_tenant_context(session, tenant_id)
            row = (
                await session.execute(
                    select(RmSyncRun).where(
                        RmSyncRun.id == run_id, RmSyncRun.tenant_id == tenant_id
                    ).with_for_update()
                )
            ).scalar_one_or_none()
            if row is None:
                raise RMSnapshotConflict("Execução não encontrada no tenant informado.")
            run = await self._hydrate_run(session, row)
            updated = stage_snapshot_page(
                run,
                offset=offset,
                next_offset=next_offset,
                records=records,
                has_more=has_more,
            )
            if updated == run:
                return updated.record_count

            canonical_page = [_canonical(record) for record in records]
            import hashlib

            fingerprint = hashlib.sha256(
                json.dumps(canonical_page, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            session.add(
                RmSyncPage(
                    run_id=run_id,
                    tenant_id=tenant_id,
                    offset=offset,
                    next_offset=next_offset,
                    fingerprint=fingerprint,
                    record_count=len(records),
                    has_more=has_more,
                    records=records,
                )
            )
            previous_keys = {key for key, _payload in run.records}
            for identity, payload in updated.records:
                if identity not in previous_keys:
                    session.add(
                        RmSyncRecord(
                            run_id=run_id,
                            tenant_id=tenant_id,
                            identity_key=identity,
                            payload=json.loads(payload),
                        )
                    )
            row.next_offset = updated.next_offset
            row.record_count = updated.record_count
            row.source_complete = updated.source_complete
            await session.flush()
            return updated.record_count

    async def finalize_run(
        self,
        session: AsyncSession,
        *,
        tenant_id: str,
        run_id: str,
        expected_record_count: int | None = None,
        authoritative_full_snapshot: bool = False,
    ) -> dict:
        async with session.begin():
            await self._set_tenant_context(session, tenant_id)
            # Lock order is always scope -> run. begin_run uses the same order.
            run_ref = (
                await session.execute(
                    select(RmSyncRun.scope_id).where(
                        RmSyncRun.id == run_id, RmSyncRun.tenant_id == tenant_id
                    )
                )
            ).scalar_one_or_none()
            if run_ref is None:
                raise RMSnapshotConflict("Execução não encontrada no tenant informado.")
            scope_row = (
                await session.execute(
                    select(RmSyncScope).where(
                        RmSyncScope.id == run_ref,
                        RmSyncScope.tenant_id == tenant_id,
                    ).with_for_update()
                )
            ).scalar_one_or_none()
            if scope_row is None:
                raise RMSnapshotConflict("Escopo não encontrado no tenant informado.")
            row = (
                await session.execute(
                    select(RmSyncRun).where(
                        RmSyncRun.id == run_id,
                        RmSyncRun.tenant_id == tenant_id,
                        RmSyncRun.scope_id == scope_row.id,
                    ).with_for_update()
                )
            ).scalar_one_or_none()
            if row is None:
                raise RMSnapshotConflict("Execução não encontrada no tenant informado.")
            run = await self._hydrate_run(session, row)
            snapshot = finalize_snapshot_run(run, expected_record_count=expected_record_count)

            previous = None
            if scope_row.current_snapshot_run_id:
                previous_row = (
                    await session.execute(
                        select(RmSyncRun).where(
                            RmSyncRun.id == scope_row.current_snapshot_run_id,
                            RmSyncRun.tenant_id == tenant_id,
                            RmSyncRun.status == "committed",
                        ).with_for_update()
                    )
                ).scalar_one_or_none()
                if previous_row:
                    previous = await self._load_committed_snapshot(session, previous_row)

            diff = reconcile_snapshots(
                previous=previous,
                current=snapshot,
                authoritative_full_snapshot=authoritative_full_snapshot,
            )
            if scope_row.current_snapshot_run_id:
                previous_row = await session.get(RmSyncRun, scope_row.current_snapshot_run_id)
                if previous_row and previous_row.tenant_id == tenant_id:
                    previous_row.status = "superseded"

            row.status = "committed"
            row.committed_at = _utc_now()
            row.expected_record_count = expected_record_count
            row.diff = {
                "added": list(diff.added),
                "updated": list(diff.updated),
                "unchanged": list(diff.unchanged),
                "removed": list(diff.removed),
            }
            scope_row.current_snapshot_run_id = run_id
            scope_row.updated_at = _utc_now()
            await session.flush()
            return row.diff

    async def get_checkpoint(
        self, session: AsyncSession, *, tenant_id: str, run_id: str
    ) -> dict | None:
        async with session.begin():
            await self._set_tenant_context(session, tenant_id)
            row = (
                await session.execute(
                    select(RmSyncRun).where(
                        RmSyncRun.id == run_id, RmSyncRun.tenant_id == tenant_id
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            return {
                "run_id": row.id,
                "status": row.status,
                "next_offset": row.next_offset,
                "record_count": row.record_count,
                "source_complete": row.source_complete,
            }

    async def _hydrate_run(self, session: AsyncSession, row: RmSyncRun) -> RMSnapshotRun:
        scope_row = await session.get(RmSyncScope, row.scope_id)
        if scope_row is None or scope_row.tenant_id != row.tenant_id:
            raise RMSnapshotConflict("Escopo persistido não corresponde ao tenant.")
        pages = (
            await session.execute(
                select(RmSyncPage).where(
                    RmSyncPage.run_id == row.id, RmSyncPage.tenant_id == row.tenant_id
                ).order_by(RmSyncPage.offset)
            )
        ).scalars().all()
        records = (
            await session.execute(
                select(RmSyncRecord).where(
                    RmSyncRecord.run_id == row.id, RmSyncRecord.tenant_id == row.tenant_id
                ).order_by(RmSyncRecord.identity_key)
            )
        ).scalars().all()
        return RMSnapshotRun(
            run_id=row.id,
            scope=RMSnapshotScope(
                tenant_id=scope_row.tenant_id,
                coligada_id=scope_row.coligada_id,
                source_name=scope_row.source_name,
                entity_name=scope_row.entity_name,
                schema_version=scope_row.schema_version,
            ),
            identity_fields=tuple(row.identity_fields),
            coligada_field=row.coligada_field,
            pages=tuple(
                RMStagedPage(
                    offset=page.offset,
                    next_offset=page.next_offset,
                    fingerprint=page.fingerprint,
                    record_count=page.record_count,
                    has_more=page.has_more,
                )
                for page in pages
            ),
            records=tuple((record.identity_key, _canonical(record.payload)) for record in records),
            next_offset=row.next_offset,
            source_complete=row.source_complete,
            deletion_semantics_confirmed=row.deletion_semantics_confirmed,
            finalized=row.status != "staging",
            record_count=row.record_count,
        )

    async def _load_committed_snapshot(
        self, session: AsyncSession, row: RmSyncRun
    ) -> RMCommittedSnapshot:
        run = await self._hydrate_run(session, row)
        return RMCommittedSnapshot(
            run_id=run.run_id,
            scope=run.scope,
            identity_fields=run.identity_fields,
            records=run.records,
            record_count=run.record_count,
            deletion_semantics_confirmed=run.deletion_semantics_confirmed,
        )
