"""Wave 13.3 — training runs, immutable snapshots, policy re-validation."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models.control_center import AdminPrincipal
from app.models.data_governance import TenantDataUsePolicy
from app.models.training_run import TrainingDatasetSnapshot, TrainingRun
from app.services.contribution_eligibility import assess_contribution
from app.services.training_run_service import (
    TrainingRunBlockedError,
    create_shared_base_training_run,
    mark_run_status,
)


def _clean_row(**overrides):
    base = {
        "attendance_rate": 0.85,
        "grade_avg": 7.2,
        "credits_completed": 40,
        "credits_enrolled": 20,
        "days_since_last_login": 3,
        "financial_delay_days": 0,
        "risk_score": 0.22,
        "engagement_score": 0.7,
        "semester": 3,
        "course_load": 20,
        "label": 0,
        "target_definition": "dropout_v1",
    }
    base.update(overrides)
    return base


async def _shared_policy(db_session, tenant_id: str, admin_id: str, slug_suffix: str):
    now = datetime.now(timezone.utc)
    db_session.add(
        TenantDataUsePolicy(
            tenant_id=tenant_id,
            mode="shared_training",
            contract_reference=f"shared-{slug_suffix}",
            contract_version="v1",
            effective_at=now - timedelta(days=1),
            approved_by_admin_id=admin_id,
            evidence_reference=f"test-evidence://{slug_suffix}",
            reason="Modalidade A",
        )
    )
    await db_session.commit()


@pytest.mark.asyncio
async def test_shared_run_requires_eligible_contributions(db_session, tenant_factory):
    tenant, _ = await tenant_factory(slug="w13-3-empty")
    admin = AdminPrincipal(
        email="w13-3-empty@example.test",
        display_name="Admin",
        password_hash="x",
        role="super_admin",
    )
    db_session.add(admin)
    await db_session.flush()
    await _shared_policy(db_session, tenant.id, admin.id, "empty")

    with pytest.raises(TrainingRunBlockedError, match="Nenhuma contribuição elegível"):
        await create_shared_base_training_run(
            db_session,
            contributing_tenant_ids=[tenant.id],
            triggered_by_admin_id=admin.id,
        )


@pytest.mark.asyncio
async def test_shared_run_creates_immutable_snapshot(db_session, tenant_factory):
    tenant, _ = await tenant_factory(slug="w13-3-ok")
    admin = AdminPrincipal(
        email="w13-3-ok@example.test",
        display_name="Admin",
        password_hash="x",
        role="super_admin",
    )
    db_session.add(admin)
    await db_session.flush()
    await _shared_policy(db_session, tenant.id, admin.id, "ok")

    await assess_contribution(
        db_session,
        tenant_id=tenant.id,
        contribution_key="batch-1",
        source_dataset_ref="test-dataset://ok",
        source_rows=[_clean_row(), _clean_row(label=1)],
        assessed_by_admin_id=admin.id,
        approval_reason="ok",
    )

    record = await create_shared_base_training_run(
        db_session,
        contributing_tenant_ids=[tenant.id],
        triggered_by_admin_id=admin.id,
        run_key="run-ok-1",
    )
    assert record.status == "queued"
    assert record.scope == "shared_base"
    assert record.dataset_hash
    assert record.row_count == 2

    snap = await db_session.get(TrainingDatasetSnapshot, record.snapshot_id)
    assert snap is not None
    assert snap.dataset_hash == record.dataset_hash
    assert tenant.id in snap.tenant_ids

    run = await db_session.get(TrainingRun, record.run_id)
    assert run is not None
    assert run.snapshot_id == snap.id

    # status transitions do not touch snapshot
    updated = await mark_run_status(
        db_session, run_id=run.id, status="running"
    )
    assert updated.status == "running"
    assert updated.started_at is not None
    snap2 = await db_session.get(TrainingDatasetSnapshot, record.snapshot_id)
    assert snap2.dataset_hash == snap.dataset_hash


@pytest.mark.asyncio
async def test_modality_b_tenant_blocks_shared_run(db_session, tenant_factory):
    tenant, _ = await tenant_factory(slug="w13-3-b")
    admin = AdminPrincipal(
        email="w13-3-b@example.test",
        display_name="Admin",
        password_hash="x",
        role="super_admin",
    )
    db_session.add(admin)
    await db_session.flush()
    now = datetime.now(timezone.utc)
    db_session.add(
        TenantDataUsePolicy(
            tenant_id=tenant.id,
            mode="institution_only",
            contract_reference="b-only",
            contract_version="v1",
            effective_at=now - timedelta(days=1),
            approved_by_admin_id=admin.id,
            evidence_reference="test-evidence://b",
            reason="B",
        )
    )
    await db_session.commit()

    with pytest.raises(TrainingRunBlockedError):
        await create_shared_base_training_run(
            db_session,
            contributing_tenant_ids=[tenant.id],
            triggered_by_admin_id=admin.id,
        )
