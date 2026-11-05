from datetime import datetime, timedelta, timezone

import pytest

from app.models.control_center import AdminPrincipal
from app.models.data_governance import TenantDataUsePolicy
from app.models.tenant import TrainingEvent
from app.ml.targets import TARGET_DEFINITION_VERSION
from app.services.shared_training_dataset import build_shared_training_dataset
from app.services.contribution_eligibility import assess_contribution
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
        await build_shared_training_dataset(
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

    assessment = await assess_contribution(
        db_session,
        tenant_id=tenant.id,
        contribution_key="shared-dataset-test",
        source_dataset_ref="test-dataset://shared",
        source_rows=[{
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
            "label": 1,
            "target_definition": "dropout_v1",
        }],
        assessed_by_admin_id=admin.id,
        approval_reason="Sanitized test contribution",
    )
    events = await build_shared_training_dataset(
        db_session,
        contributing_tenant_ids=[tenant.id],
        dataset_eligibility={tenant.id: True},
    )
    assert assessment.status == "eligible"
    assert len(events) == 1
    assert events[0].contribution_id_hash == assessment.sanitized_content_hash
    assert events[0].tenant_contribution_hash == f"{tenant.id}:{assessment.sanitized_content_hash}"
