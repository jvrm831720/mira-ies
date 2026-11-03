"""PostgreSQL integration tests for durable TOTVS RM snapshot synchronization."""

import pytest
from sqlalchemy import func, select, text

from app.db.session import AsyncSessionLocal
from app.models.rm_sync import RmSyncPage, RmSyncRecord, RmSyncRun
from app.services.connectors.totvs_rm_snapshot_repository import (
    RMPostgresSnapshotRepository,
    RMSnapshotConflict,
)
from app.services.connectors.totvs_rm_snapshot_sync import (
    RMSourceSyncContract,
    RMSnapshotScope,
)


@pytest.fixture
def sync_contract():
    return RMSourceSyncContract(
        source_name="EduParcelaData",
        entity_name="installments",
        identity_fields=("CODCOLIGADA", "IDPARCELA"),
        coligada_field="CODCOLIGADA",
        supports_full_snapshot=True,
        deletion_semantics_confirmed=True,
    )


def _scope(tenant_id):
    return RMSnapshotScope(
        tenant_id=str(tenant_id),
        coligada_id="1",
        source_name="EduParcelaData",
        entity_name="installments",
        schema_version="v1",
    )


@pytest.mark.asyncio
async def test_persists_checkpoint_and_resumes_after_new_session(db_session, tenant, sync_contract):
    tenant_row, _ = tenant
    repo = RMPostgresSnapshotRepository()
    scope = _scope(tenant_row.id)
    await db_session.rollback()  # tenant fixture refresh opens a read transaction

    await repo.begin_run(
        db_session, run_id="10000000-0000-0000-0000-000000000001",
        scope=scope, contract=sync_contract,
    )
    await repo.stage_page(
        db_session,
        tenant_id=scope.tenant_id,
        run_id="10000000-0000-0000-0000-000000000001",
        offset=0,
        next_offset=1,
        records=[{"CODCOLIGADA": 1, "IDPARCELA": "0001", "VALOR": "10.00"}],
        has_more=True,
    )
    replay_count = await repo.stage_page(
        db_session,
        tenant_id=scope.tenant_id,
        run_id="10000000-0000-0000-0000-000000000001",
        offset=0,
        next_offset=1,
        records=[{"CODCOLIGADA": 1, "IDPARCELA": "0001", "VALOR": "10.00"}],
        has_more=True,
    )
    assert replay_count == 1
    checkpoint = await repo.get_checkpoint(
        db_session, tenant_id=scope.tenant_id,
        run_id="10000000-0000-0000-0000-000000000001",
    )
    assert checkpoint["next_offset"] == 1
    assert checkpoint["record_count"] == 1
    await db_session.rollback()

    # A separate session proves that the page and checkpoint survived process/session loss.
    async with AsyncSessionLocal() as resumed:
        await repo.stage_page(
            resumed,
            tenant_id=scope.tenant_id,
            run_id="10000000-0000-0000-0000-000000000001",
            offset=1,
            next_offset=2,
            records=[{"CODCOLIGADA": 1, "IDPARCELA": "0002", "VALOR": "20.00"}],
            has_more=False,
        )
        diff = await repo.finalize_run(
            resumed,
            tenant_id=scope.tenant_id,
            run_id="10000000-0000-0000-0000-000000000001",
            expected_record_count=2,
            authoritative_full_snapshot=True,
        )
        assert len(diff["added"]) == 2
        assert diff["removed"] == []


@pytest.mark.asyncio
async def test_publish_is_atomic_and_supersedes_previous_snapshot(db_session, tenant, sync_contract):
    tenant_row, _ = tenant
    repo = RMPostgresSnapshotRepository()
    scope = _scope(tenant_row.id)
    await db_session.rollback()  # tenant fixture refresh opens a read transaction
    first_id = "10000000-0000-0000-0000-000000000002"
    second_id = "10000000-0000-0000-0000-000000000003"

    await repo.begin_run(db_session, run_id=first_id, scope=scope, contract=sync_contract)
    await repo.stage_page(
        db_session, tenant_id=scope.tenant_id, run_id=first_id,
        offset=0, next_offset=2,
        records=[
            {"CODCOLIGADA": 1, "IDPARCELA": "1", "VALOR": "10.00"},
            {"CODCOLIGADA": 1, "IDPARCELA": "2", "VALOR": "20.00"},
        ],
        has_more=False,
    )
    await repo.finalize_run(
        db_session, tenant_id=scope.tenant_id, run_id=first_id,
        expected_record_count=2, authoritative_full_snapshot=True,
    )

    await repo.begin_run(db_session, run_id=second_id, scope=scope, contract=sync_contract)
    await repo.stage_page(
        db_session, tenant_id=scope.tenant_id, run_id=second_id,
        offset=0, next_offset=2,
        records=[
            {"CODCOLIGADA": 1, "IDPARCELA": "1", "VALOR": "15.00"},
            {"CODCOLIGADA": 1, "IDPARCELA": "3", "VALOR": "30.00"},
        ],
        has_more=False,
    )
    diff = await repo.finalize_run(
        db_session, tenant_id=scope.tenant_id, run_id=second_id,
        expected_record_count=2, authoritative_full_snapshot=True,
    )

    assert len(diff["added"]) == 1
    assert len(diff["updated"]) == 1
    assert len(diff["removed"]) == 1
    first = await repo.get_checkpoint(
        db_session, tenant_id=scope.tenant_id, run_id=first_id
    )
    second = await repo.get_checkpoint(
        db_session, tenant_id=scope.tenant_id, run_id=second_id
    )
    assert first["status"] == "superseded"
    assert second["status"] == "committed"


@pytest.mark.asyncio
async def test_incomplete_snapshot_cannot_publish_and_transaction_rolls_back(db_session, tenant, sync_contract):
    tenant_row, _ = tenant
    repo = RMPostgresSnapshotRepository()
    scope = _scope(tenant_row.id)
    await db_session.rollback()  # tenant fixture refresh opens a read transaction
    run_id = "10000000-0000-0000-0000-000000000004"

    await repo.begin_run(db_session, run_id=run_id, scope=scope, contract=sync_contract)
    await repo.stage_page(
        db_session, tenant_id=scope.tenant_id, run_id=run_id,
        offset=0, next_offset=1,
        records=[{"CODCOLIGADA": 1, "IDPARCELA": "1"}],
        has_more=True,
    )
    with pytest.raises(ValueError, match="incompleto"):
        await repo.finalize_run(
            db_session, tenant_id=scope.tenant_id, run_id=run_id,
            authoritative_full_snapshot=True,
        )
    checkpoint = await repo.get_checkpoint(
        db_session, tenant_id=scope.tenant_id, run_id=run_id
    )
    assert checkpoint["status"] == "staging"
    assert checkpoint["next_offset"] == 1


@pytest.mark.asyncio
async def test_one_staging_run_per_scope_and_tenant_filter(db_session, tenant, sync_contract):
    tenant_row, _ = tenant
    repo = RMPostgresSnapshotRepository()
    scope = _scope(tenant_row.id)
    await db_session.rollback()  # tenant fixture refresh opens a read transaction
    await repo.begin_run(
        db_session,
        run_id="10000000-0000-0000-0000-000000000005",
        scope=scope,
        contract=sync_contract,
    )
    with pytest.raises(RMSnapshotConflict, match="Já existe"):
        await repo.begin_run(
            db_session,
            run_id="10000000-0000-0000-0000-000000000006",
            scope=scope,
            contract=sync_contract,
        )
    assert await repo.get_checkpoint(
        db_session,
        tenant_id="00000000-0000-0000-0000-000000000099",
        run_id="10000000-0000-0000-0000-000000000005",
    ) is None


@pytest.mark.asyncio
async def test_abort_run_purges_partial_snapshot_data(db_session, tenant, sync_contract):
    tenant_row, _ = tenant
    repo = RMPostgresSnapshotRepository()
    scope = _scope(tenant_row.id)
    run_id = "10000000-0000-0000-0000-000000000007"
    await db_session.rollback()
    await repo.begin_run(db_session, run_id=run_id, scope=scope, contract=sync_contract)
    await repo.stage_page(
        db_session, tenant_id=scope.tenant_id, run_id=run_id,
        offset=0, next_offset=1,
        records=[{"CODCOLIGADA": 1, "IDPARCELA": "0001", "VALOR": "10.00"}],
        has_more=True,
    )
    await repo.abort_run(tenant_id=scope.tenant_id, run_id=run_id, reason="cancelled")
    checkpoint = await repo.get_checkpoint(
        db_session, tenant_id=scope.tenant_id, run_id=run_id
    )
    assert checkpoint["status"] == "failed"
    assert checkpoint["record_count"] == 0
    await db_session.rollback()
    async with AsyncSessionLocal() as session, session.begin():
        await session.execute(
            text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
            {"tenant_id": scope.tenant_id},
        )
        page_count = (await session.execute(
            select(func.count()).select_from(RmSyncPage).where(
                RmSyncPage.run_id == run_id, RmSyncPage.tenant_id == scope.tenant_id
            )
        )).scalar_one()
        record_count = (await session.execute(
            select(func.count()).select_from(RmSyncRecord).where(
                RmSyncRecord.run_id == run_id, RmSyncRecord.tenant_id == scope.tenant_id
            )
        )).scalar_one()
    assert page_count == 0
    assert record_count == 0
