"""Wave 13.4 — MIRA Base approve / activate / rollback."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.models.control_center import AdminPrincipal
from app.models.training_run import TrainingDatasetSnapshot, TrainingRun
from app.services.mira_base_lifecycle import (
    MiraBaseLifecycleError,
    activate_base,
    approve_base,
    get_active_base,
    register_base_candidate,
    reject_base,
    rollback_base,
)


async def _admin(db_session, email: str) -> AdminPrincipal:
    admin = AdminPrincipal(
        email=email,
        display_name="Lifecycle Admin",
        password_hash="x",
        role="super_admin",
    )
    db_session.add(admin)
    await db_session.flush()
    return admin


async def _succeeded_shared_run(db_session, admin_id: str) -> TrainingRun:
    now = datetime.now(timezone.utc)
    snap = TrainingDatasetSnapshot(
        id=str(uuid4()),
        scope="shared_base",
        dataset_hash=f"hash-{uuid4().hex[:16]}",
        contribution_hashes=["c1", "c2"],
        tenant_ids=[str(uuid4())],
        row_count=10,
        anonymization_rules_version="anon-v1",
        feature_schema_version="features-v1",
        built_by_admin_id=admin_id,
        built_at=now,
    )
    db_session.add(snap)
    await db_session.flush()
    run = TrainingRun(
        id=str(uuid4()),
        run_key=f"run-{uuid4().hex[:8]}",
        scope="shared_base",
        tenant_id=None,
        snapshot_id=snap.id,
        dataset_hash=snap.dataset_hash,
        status="succeeded",
        triggered_by_admin_id=admin_id,
        started_at=now,
        finished_at=now,
        metrics={"auc": 0.81},
    )
    db_session.add(run)
    await db_session.commit()
    return run


@pytest.mark.asyncio
async def test_register_requires_succeeded_shared_run(db_session):
    admin = await _admin(db_session, "w13-4-fail@example.test")
    now = datetime.now(timezone.utc)
    snap = TrainingDatasetSnapshot(
        id=str(uuid4()),
        scope="shared_base",
        dataset_hash="h-queued",
        contribution_hashes=[],
        tenant_ids=[],
        row_count=0,
        anonymization_rules_version="anon-v1",
        feature_schema_version="features-v1",
        built_at=now,
    )
    db_session.add(snap)
    await db_session.flush()
    run = TrainingRun(
        id=str(uuid4()),
        run_key="queued-only",
        scope="shared_base",
        snapshot_id=snap.id,
        dataset_hash="h-queued",
        status="queued",
    )
    db_session.add(run)
    await db_session.commit()

    with pytest.raises(MiraBaseLifecycleError, match="succeeded"):
        await register_base_candidate(
            db_session,
            name="MIRA Base",
            version="1.0.0",
            run_id=run.id,
            actor_admin_id=admin.id,
        )


@pytest.mark.asyncio
async def test_approve_activate_and_rollback(db_session):
    admin = await _admin(db_session, "w13-4-ok@example.test")
    run1 = await _succeeded_shared_run(db_session, admin.id)
    run2 = await _succeeded_shared_run(db_session, admin.id)

    c1 = await register_base_candidate(
        db_session,
        name="MIRA Base",
        version="1.0.0",
        run_id=run1.id,
        actor_admin_id=admin.id,
        metrics={"auc": 0.80},
    )
    assert c1.lifecycle_status == "candidate"

    approved = await approve_base(
        db_session, artifact_id=c1.artifact_id, actor_admin_id=admin.id, reason="Métricas ok"
    )
    assert approved.lifecycle_status == "approved"

    active = await activate_base(
        db_session, artifact_id=c1.artifact_id, actor_admin_id=admin.id, reason="Ativar v1"
    )
    assert active.is_active is True
    assert active.lifecycle_status == "active"
    assert (await get_active_base(db_session)).artifact_id == c1.artifact_id

    c2 = await register_base_candidate(
        db_session,
        name="MIRA Base",
        version="1.1.0",
        run_id=run2.id,
        actor_admin_id=admin.id,
        metrics={"auc": 0.85},
    )
    await approve_base(
        db_session, artifact_id=c2.artifact_id, actor_admin_id=admin.id, reason="Melhor AUC"
    )
    active2 = await activate_base(
        db_session, artifact_id=c2.artifact_id, actor_admin_id=admin.id, reason="Ativar v1.1"
    )
    assert active2.artifact_id == c2.artifact_id
    assert (await get_active_base(db_session)).artifact_id == c2.artifact_id

    # Rollback to v1
    rolled = await rollback_base(
        db_session,
        target_artifact_id=c1.artifact_id,
        actor_admin_id=admin.id,
        reason="Regressão detectada",
    )
    assert rolled.artifact_id == c1.artifact_id
    assert rolled.is_active is True
    assert (await get_active_base(db_session)).artifact_id == c1.artifact_id


@pytest.mark.asyncio
async def test_cannot_activate_unapproved(db_session):
    admin = await _admin(db_session, "w13-4-unapproved@example.test")
    run = await _succeeded_shared_run(db_session, admin.id)
    c = await register_base_candidate(
        db_session,
        name="MIRA Base",
        version="0.9.0",
        run_id=run.id,
        actor_admin_id=admin.id,
    )
    with pytest.raises(MiraBaseLifecycleError, match="approved"):
        await activate_base(
            db_session, artifact_id=c.artifact_id, actor_admin_id=admin.id, reason="skip"
        )


@pytest.mark.asyncio
async def test_reject_candidate(db_session):
    admin = await _admin(db_session, "w13-4-reject@example.test")
    run = await _succeeded_shared_run(db_session, admin.id)
    c = await register_base_candidate(
        db_session,
        name="MIRA Base",
        version="0.8.0",
        run_id=run.id,
        actor_admin_id=admin.id,
    )
    rejected = await reject_base(
        db_session, artifact_id=c.artifact_id, actor_admin_id=admin.id, reason="AUC baixo"
    )
    assert rejected.lifecycle_status == "rejected"
