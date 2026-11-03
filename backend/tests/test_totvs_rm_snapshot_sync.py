"""Synthetic tests for safe TOTVS RM snapshot staging and reconciliation."""

from dataclasses import replace

import pytest

from app.services.connectors.totvs_rm_snapshot_sync import (
    RMSourceSyncContract,
    RMSnapshotScope,
    begin_snapshot_run,
    finalize_snapshot_run,
    reconcile_snapshots,
    stage_snapshot_page,
)


@pytest.fixture
def contract():
    return RMSourceSyncContract(
        source_name="EduParcelaData",
        entity_name="installments",
        identity_fields=("CODCOLIGADA", "IDPARCELA"),
        coligada_field="CODCOLIGADA",
        supports_full_snapshot=True,
        deletion_semantics_confirmed=True,
    )


@pytest.fixture
def scope():
    return RMSnapshotScope(
        tenant_id="tenant-a",
        coligada_id="1",
        source_name="EduParcelaData",
        entity_name="installments",
        schema_version="v1",
    )


def _snapshot(run_id, scope, contract, rows):
    run = begin_snapshot_run(run_id=run_id, scope=scope, contract=contract)
    run = stage_snapshot_page(
        run, offset=0, next_offset=len(rows), records=rows, has_more=False
    )
    return finalize_snapshot_run(run, expected_record_count=len(rows))


def test_full_snapshot_pages_checkpoint_and_atomic_finalize(contract, scope):
    run = begin_snapshot_run(run_id="run-1", scope=scope, contract=contract)
    run = stage_snapshot_page(
        run,
        offset=0,
        next_offset=2,
        records=[
            {"CODCOLIGADA": 1, "IDPARCELA": "0001"},
            {"CODCOLIGADA": 1, "IDPARCELA": "0002"},
        ],
        has_more=True,
    )
    assert run.next_offset == 2
    with pytest.raises(ValueError, match="incompleto"):
        finalize_snapshot_run(run)

    run = stage_snapshot_page(
        run,
        offset=2,
        next_offset=3,
        records=[{"CODCOLIGADA": 1, "IDPARCELA": "0003"}],
        has_more=False,
    )
    snapshot = finalize_snapshot_run(run, expected_record_count=3)
    assert snapshot.record_count == 3
    assert len(snapshot.records) == 3
    assert stage_snapshot_page(
        run,
        offset=2,
        next_offset=3,
        records=[{"CODCOLIGADA": 1, "IDPARCELA": "0003"}],
        has_more=False,
    ) == run


def test_page_replay_is_idempotent_and_conflicting_replay_is_rejected(contract, scope):
    run = begin_snapshot_run(run_id="run-1", scope=scope, contract=contract)
    page = [{"CODCOLIGADA": 1, "IDPARCELA": "0001"}]
    run = stage_snapshot_page(
        run, offset=0, next_offset=1, records=page, has_more=True
    )
    replay = stage_snapshot_page(
        run, offset=0, next_offset=1, records=page, has_more=True
    )
    assert replay == run
    with pytest.raises(ValueError, match="replay divergente"):
        stage_snapshot_page(
            run,
            offset=0,
            next_offset=1,
            records=[{"CODCOLIGADA": 1, "IDPARCELA": "changed"}],
            has_more=True,
        )
    with pytest.raises(ValueError, match="replay divergente"):
        stage_snapshot_page(
            run, offset=0, next_offset=1, records=page, has_more=False
        )


def test_rejects_out_of_order_pages_and_duplicate_identity(contract, scope):
    run = begin_snapshot_run(run_id="run-1", scope=scope, contract=contract)
    with pytest.raises(ValueError, match="Checkpoint fora"):
        stage_snapshot_page(
            run, offset=10, next_offset=11,
            records=[{"CODCOLIGADA": 1, "IDPARCELA": "1"}],
            has_more=False,
        )
    with pytest.raises(ValueError, match="duplicada"):
        stage_snapshot_page(
            run, offset=0, next_offset=2,
            records=[
                {"CODCOLIGADA": 1, "IDPARCELA": "1"},
                {"CODCOLIGADA": "1", "IDPARCELA": "1"},
            ],
            has_more=False,
        )


def test_rejects_record_from_another_coligada(contract, scope):
    run = begin_snapshot_run(run_id="run-1", scope=scope, contract=contract)
    with pytest.raises(ValueError, match="outra coligada"):
        stage_snapshot_page(
            run,
            offset=0,
            next_offset=1,
            records=[{"CODCOLIGADA": 2, "IDPARCELA": "1"}],
            has_more=False,
        )


def test_missing_identity_and_invalid_json_values_are_rejected(contract, scope):
    run = begin_snapshot_run(run_id="run-1", scope=scope, contract=contract)
    with pytest.raises(ValueError, match="Identidade"):
        stage_snapshot_page(
            run, offset=0, next_offset=1,
            records=[{"CODCOLIGADA": 1}], has_more=False,
        )
    with pytest.raises(ValueError, match="JSON válidos"):
        stage_snapshot_page(
            run, offset=0, next_offset=1,
            records=[{"CODCOLIGADA": 1, "IDPARCELA": "1", "BAD": object()}],
            has_more=False,
        )


def test_expected_count_mismatch_blocks_commit(contract, scope):
    run = _snapshot("run-1", scope, contract, [{"CODCOLIGADA": 1, "IDPARCELA": "1"}])
    assert run.record_count == 1
    run = begin_snapshot_run(run_id="run-2", scope=scope, contract=contract)
    run = stage_snapshot_page(
        run,
        offset=0,
        next_offset=1,
        records=[{"CODCOLIGADA": 1, "IDPARCELA": "1"}],
        has_more=False,
    )
    with pytest.raises(ValueError, match="diverge"):
        finalize_snapshot_run(run, expected_record_count=2)


def test_diff_detects_added_updated_unchanged_and_removed(contract, scope):
    previous = _snapshot(
        "run-1", scope, contract,
        [
            {"CODCOLIGADA": 1, "IDPARCELA": "1", "VALOR": "10.00"},
            {"CODCOLIGADA": 1, "IDPARCELA": "2", "VALOR": "20.00"},
            {"CODCOLIGADA": 1, "IDPARCELA": "3", "VALOR": "30.00"},
        ],
    )
    current = _snapshot(
        "run-2", scope, contract,
        [
            {"CODCOLIGADA": 1, "IDPARCELA": "1", "VALOR": "10.00"},
            {"CODCOLIGADA": 1, "IDPARCELA": "2", "VALOR": "25.00"},
            {"CODCOLIGADA": 1, "IDPARCELA": "4", "VALOR": "40.00"},
        ],
    )
    partial = reconcile_snapshots(
        previous=previous, current=current, authoritative_full_snapshot=False
    )
    assert partial.added == ('["1","4"]',)
    assert partial.updated == ('["1","2"]',)
    assert partial.unchanged == ('["1","1"]',)
    assert partial.removed == ()

    authoritative = reconcile_snapshots(
        previous=previous, current=current, authoritative_full_snapshot=True
    )
    assert authoritative.removed == ('["1","3"]',)

    unverified_contract = replace(contract, deletion_semantics_confirmed=False)
    unverified_current = _snapshot(
        "run-3",
        scope,
        unverified_contract,
        [{"CODCOLIGADA": 1, "IDPARCELA": "1", "VALOR": "10.00"}],
    )
    unverified_diff = reconcile_snapshots(
        previous=previous,
        current=unverified_current,
        authoritative_full_snapshot=True,
    )
    assert unverified_diff.removed == ()


def test_snapshot_scope_isolation_and_contract_gate(contract, scope):
    other_scope = RMSnapshotScope(
        tenant_id="tenant-b",
        coligada_id="1",
        source_name="EduParcelaData",
        entity_name="installments",
        schema_version="v1",
    )
    previous = _snapshot("run-1", scope, contract, [{"CODCOLIGADA": 1, "IDPARCELA": "1"}])
    current = _snapshot(
        "run-2", other_scope, contract, [{"CODCOLIGADA": 1, "IDPARCELA": "1"}]
    )
    with pytest.raises(ValueError, match="tenants"):
        reconcile_snapshots(
            previous=previous, current=current, authoritative_full_snapshot=True
        )

    unsupported = RMSourceSyncContract(
        source_name="EduParcelaData",
        entity_name="installments",
        identity_fields=("CODCOLIGADA", "IDPARCELA"),
        coligada_field="CODCOLIGADA",
        supports_full_snapshot=False,
    )
    with pytest.raises(ValueError, match="extração completa"):
        begin_snapshot_run(run_id="run-3", scope=scope, contract=unsupported)


def test_incremental_contract_requires_explicit_cursor_and_stable_order():
    with pytest.raises(ValueError, match="cursor homologado"):
        RMSourceSyncContract(
            source_name="EduParcelaData",
            entity_name="installments",
            identity_fields=("CODCOLIGADA", "IDPARCELA"),
            coligada_field="CODCOLIGADA",
            supports_full_snapshot=True,
            supports_incremental=True,
        )
