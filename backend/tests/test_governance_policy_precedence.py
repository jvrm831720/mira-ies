from datetime import datetime, timedelta, timezone

import pytest

from app.models.control_center import AdminPrincipal
from app.models.data_governance import TenantDataUsePolicy
from app.models.institutional_training_authorization import InstitutionalTrainingAuthorization
from app.services.training_policy import (
    resolve_institutional_training_authorization,
    resolve_training_policy,
)


@pytest.mark.asyncio
async def test_new_revocation_supersedes_older_future_scheduled_shared_policy(db_session, tenant_factory):
    tenant, _ = await tenant_factory(slug="governance-revoke-future-shared")
    admin = AdminPrincipal(
        email="governance-revoke-shared@example.test",
        display_name="Governance Admin",
        password_hash="not-a-real-password-hash",
        role="super_admin",
    )
    db_session.add(admin)
    await db_session.flush()
    now = datetime.now(timezone.utc)

    current = TenantDataUsePolicy(
        tenant_id=tenant.id, mode="shared_training",
        contract_reference="contract-current", contract_version="v1",
        effective_at=now - timedelta(days=2), created_at=now - timedelta(days=2),
        approved_by_admin_id=admin.id, evidence_reference="test-evidence://current",
    )
    future = TenantDataUsePolicy(
        tenant_id=tenant.id, mode="shared_training",
        contract_reference="contract-future", contract_version="v2",
        effective_at=now + timedelta(days=2), created_at=now - timedelta(hours=1),
        approved_by_admin_id=admin.id, evidence_reference="test-evidence://future",
    )
    revocation = TenantDataUsePolicy(
        tenant_id=tenant.id, mode="shared_training",
        contract_reference="contract-future", contract_version="v2",
        effective_at=now - timedelta(minutes=1), created_at=now,
        revoked_at=now - timedelta(minutes=1), approved_by_admin_id=admin.id,
        evidence_reference="test-evidence://future", reason="Consentimento revogado.",
    )
    db_session.add_all([current, future, revocation])
    await db_session.commit()

    decision = await resolve_training_policy(
        db_session, tenant_id=tenant.id, purpose="shared_base_training",
        dataset_eligible=True, now=now,
    )
    assert not decision.allowed
    assert decision.policy_id == revocation.id
    assert "revoked" in decision.reason.lower()


@pytest.mark.asyncio
async def test_new_revocation_supersedes_older_future_scheduled_institutional_authorization(
    db_session, tenant_factory
):
    tenant, _ = await tenant_factory(slug="governance-revoke-future-local")
    admin = AdminPrincipal(
        email="governance-revoke-local@example.test",
        display_name="Governance Admin",
        password_hash="not-a-real-password-hash",
        role="super_admin",
    )
    db_session.add(admin)
    await db_session.flush()
    now = datetime.now(timezone.utc)

    current = InstitutionalTrainingAuthorization(
        tenant_id=tenant.id, contract_reference="local-current", contract_version="v1",
        effective_at=now - timedelta(days=2), created_at=now - timedelta(days=2),
        approved_by_admin_id=admin.id, evidence_reference="test-evidence://local-current",
        dataset_eligibility_reference="test-dataset://local-current",
    )
    future = InstitutionalTrainingAuthorization(
        tenant_id=tenant.id, contract_reference="local-future", contract_version="v2",
        effective_at=now + timedelta(days=2), created_at=now - timedelta(hours=1),
        approved_by_admin_id=admin.id, evidence_reference="test-evidence://local-future",
        dataset_eligibility_reference="test-dataset://local-future",
    )
    revocation = InstitutionalTrainingAuthorization(
        tenant_id=tenant.id, contract_reference="local-future", contract_version="v2",
        effective_at=now - timedelta(minutes=1), created_at=now,
        revoked_at=now - timedelta(minutes=1), approved_by_admin_id=admin.id,
        evidence_reference="test-evidence://local-future",
        dataset_eligibility_reference="test-dataset://local-future",
        reason="Autorização revogada.",
    )
    db_session.add_all([current, future, revocation])
    await db_session.commit()

    decision = await resolve_institutional_training_authorization(
        db_session, tenant_id=tenant.id, now=now
    )
    assert not decision.allowed
    assert decision.authorization_id == revocation.id
    assert "revoked" in decision.reason.lower()
