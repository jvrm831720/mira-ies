from datetime import datetime, timedelta, timezone

import pytest

from app.models.control_center import AdminPrincipal
from app.models.data_governance import TenantDataUsePolicy
from app.models.tenant import TrainingEvent
from app.ml.targets import TARGET_DEFINITION_VERSION
from app.services.shared_training_dataset import build_shared_training_events
from app.services.shared_training_guard import SharedTrainingBlockedError


async def _policy(db_session, tenant_id, admin_id, mode, suffix):
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
async def test_institution_only_events_never_enter_shared_dataset(db_session, tenant_factory):
    tenant, _ = await tenant_factory(slug="dataset-institution-only")
    admin = AdminPrincipal(
        email="dataset-local-admin@example.test",
        display_name="Policy Admin",
        password_hash="not-a-real-password-hash",
        role="super_admin",
    )
    db_session.add(admin)
    await db_session.flush()
    await _policy(db_session, tenant.id, admin.id, "institution_only", "local")
    db_session.add(TrainingEvent(
        tenant_id=tenant.id,
        matricula="LOCAL-001",
        features_snapshot={"dias_atraso_boleto": 20},
        label=1,
        target_definition=TARGET_DEFINITION_VERSION,
    ))
    await db_session.commit()

    with pytest.raises(SharedTrainingBlockedError):
        await build_shared_training_events(
            db_session,
            contributing_tenant_ids=[tenant.id],
            dataset_eligibility={tenant.id: True},
        )


@pytest.mark.asyncio
async def test_shared_dataset_only_contains_explicitly_authorized_tenants(db_session, tenant_factory):
    tenant, _ = await tenant_factory(slug="dataset-shared")
    admin = AdminPrincipal(
        email="dataset-shared-admin@example.test",
        display_name="Policy Admin",
        password_hash="not-a-real-password-hash",
        role="super_admin",
    )
    db_session.add(admin)
    await db_session.flush()
    await _policy(db_session, tenant.id, admin.id, "shared_training", "shared")
    db_session.add(TrainingEvent(
        tenant_id=tenant.id,
        matricula="SHARED-001",
        features_snapshot={"dias_atraso_boleto": 20},
        label=1,
        target_definition=TARGET_DEFINITION_VERSION,
    ))
    await db_session.commit()

    events = await build_shared_training_events(
        db_session,
        contributing_tenant_ids=[tenant.id],
        dataset_eligibility={tenant.id: True},
    )
    assert [event.tenant_id for event in events] == [tenant.id]
