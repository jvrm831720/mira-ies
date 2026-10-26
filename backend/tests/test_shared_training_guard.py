from datetime import datetime, timedelta, timezone

import pytest

from app.models.control_center import AdminPrincipal
from app.models.data_governance import TenantDataUsePolicy
from app.services.shared_training_guard import (
    SharedTrainingBlockedError,
    require_shared_training_authorization,
)


async def _add_policy(db_session, tenant_id: str, admin_id: str, mode: str, suffix: str):
    db_session.add(TenantDataUsePolicy(
        tenant_id=tenant_id,
        mode=mode,
        contract_reference=f"contract-{suffix}",
        contract_version="v1",
        effective_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        approved_by_admin_id=admin_id,
        evidence_reference=f"test-evidence://{suffix}",
    ))
    await db_session.flush()


@pytest.mark.asyncio
async def test_shared_training_guard_fails_closed_for_missing_policy(db_session, tenant_factory):
    tenant, _ = await tenant_factory(slug="shared-guard-missing")

    with pytest.raises(SharedTrainingBlockedError, match="política vigente"):
        await require_shared_training_authorization(
            db_session,
            contributing_tenant_ids=[tenant.id],
            dataset_eligibility={tenant.id: True},
        )


@pytest.mark.asyncio
async def test_shared_training_guard_blocks_institution_only_contributor(db_session, tenant_factory):
    tenant, _ = await tenant_factory(slug="shared-guard-local")
    admin = AdminPrincipal(
        email="shared-guard-admin@example.test",
        display_name="Policy Admin",
        password_hash="not-a-real-password-hash",
        role="super_admin",
    )
    db_session.add(admin)
    await db_session.flush()
    await _add_policy(db_session, tenant.id, admin.id, "institution_only", "local-only")
    await db_session.commit()

    with pytest.raises(SharedTrainingBlockedError, match="Institution-only policy blocks shared training"):
        await require_shared_training_authorization(
            db_session,
            contributing_tenant_ids=[tenant.id],
            dataset_eligibility={tenant.id: True},
        )


@pytest.mark.asyncio
async def test_shared_training_guard_blocks_entire_batch_if_any_contributor_is_denied(
    db_session, tenant_factory
):
    shared_tenant, _ = await tenant_factory(slug="shared-guard-consented")
    local_tenant, _ = await tenant_factory(slug="shared-guard-private")
    admin = AdminPrincipal(
        email="shared-guard-mixed-admin@example.test",
        display_name="Policy Admin",
        password_hash="not-a-real-password-hash",
        role="super_admin",
    )
    db_session.add(admin)
    await db_session.flush()
    await _add_policy(db_session, shared_tenant.id, admin.id, "shared_training", "shared")
    await _add_policy(db_session, local_tenant.id, admin.id, "institution_only", "private")
    await db_session.commit()

    with pytest.raises(SharedTrainingBlockedError, match=local_tenant.id):
        await require_shared_training_authorization(
            db_session,
            contributing_tenant_ids=[shared_tenant.id, local_tenant.id],
            dataset_eligibility={
                shared_tenant.id: True,
                local_tenant.id: True,
            },
        )


@pytest.mark.asyncio
async def test_shared_training_guard_requires_eligibility_for_every_contributor(
    db_session, tenant_factory
):
    tenant, _ = await tenant_factory(slug="shared-guard-no-eligibility")
    admin = AdminPrincipal(
        email="shared-guard-eligibility-admin@example.test",
        display_name="Policy Admin",
        password_hash="not-a-real-password-hash",
        role="super_admin",
    )
    db_session.add(admin)
    await db_session.flush()
    await _add_policy(db_session, tenant.id, admin.id, "shared_training", "eligibility")
    await db_session.commit()

    with pytest.raises(SharedTrainingBlockedError, match="Dataset is not eligible"):
        await require_shared_training_authorization(
            db_session,
            contributing_tenant_ids=[tenant.id],
        )


@pytest.mark.asyncio
async def test_shared_training_guard_rejects_empty_contributor_set(db_session):
    with pytest.raises(SharedTrainingBlockedError, match="lista de instituições"):
        await require_shared_training_authorization(
            db_session,
            contributing_tenant_ids=[],
        )
