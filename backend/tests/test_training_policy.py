from datetime import datetime, timedelta, timezone
import pytest

from app.models.control_center import AdminPrincipal
from app.models.data_governance import TenantDataUsePolicy
from app.services.training_policy import resolve_training_policy


@pytest.mark.asyncio
async def test_missing_policy_requires_sharing_consent_and_local_authorization(db_session, tenant_factory):
    tenant, _ = await tenant_factory(slug="policy-missing")
    shared = await resolve_training_policy(
        db_session, tenant_id=tenant.id, purpose="shared_base_training",
        dataset_eligible=True,
    )
    local_without_authorization = await resolve_training_policy(
        db_session, tenant_id=tenant.id, purpose="institutional_training",
        dataset_eligible=True,
    )
    local_authorized = await resolve_training_policy(
        db_session, tenant_id=tenant.id, purpose="institutional_training",
        dataset_eligible=True, institutional_use_authorized=True,
    )
    assert not shared.allowed
    assert shared.policy_id is None
    assert not local_without_authorization.allowed
    assert local_authorized.allowed


@pytest.mark.asyncio
async def test_shared_mode_allows_only_eligible_dataset(db_session, tenant_factory):
    tenant, _ = await tenant_factory(slug="policy-shared")
    admin = AdminPrincipal(
        email="policy-admin@example.test",
        display_name="Policy Admin",
        password_hash="not-a-real-password-hash",
        role="super_admin",
    )
    db_session.add(admin)
    await db_session.flush()
    policy = TenantDataUsePolicy(
        tenant_id=tenant.id, mode="shared_training",
        contract_reference="contract-001", contract_version="v1",
        effective_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        approved_by_admin_id=admin.id,
        evidence_reference="test-evidence://contract-001",
    )
    db_session.add(policy)
    await db_session.commit()

    eligible = await resolve_training_policy(
        db_session, tenant_id=tenant.id, purpose="shared_base_training",
        dataset_eligible=True,
    )
    ineligible = await resolve_training_policy(
        db_session, tenant_id=tenant.id, purpose="shared_base_training",
        dataset_eligible=False,
    )
    assert eligible.allowed
    assert eligible.policy_id == policy.id
    assert not ineligible.allowed


@pytest.mark.asyncio
async def test_institution_only_blocks_shared_but_permits_eligible_local_training(db_session, tenant_factory):
    tenant, _ = await tenant_factory(slug="policy-local")
    admin = AdminPrincipal(
        email="policy-local-admin@example.test",
        display_name="Policy Admin",
        password_hash="not-a-real-password-hash",
        role="super_admin",
    )
    db_session.add(admin)
    await db_session.flush()
    policy = TenantDataUsePolicy(
        tenant_id=tenant.id, mode="institution_only",
        contract_reference="contract-002", contract_version="v1",
        effective_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        approved_by_admin_id=admin.id,
        evidence_reference="test-evidence://contract-002",
    )
    db_session.add(policy)
    await db_session.commit()

    shared = await resolve_training_policy(
        db_session, tenant_id=tenant.id, purpose="shared_base_training",
        dataset_eligible=True,
    )
    local = await resolve_training_policy(
        db_session, tenant_id=tenant.id, purpose="institutional_training",
        dataset_eligible=True, institutional_use_authorized=True,
    )
    assert not shared.allowed
    assert local.allowed


@pytest.mark.asyncio
async def test_expired_or_revoked_policy_denies_shared_training(db_session, tenant_factory):
    tenant, _ = await tenant_factory(slug="policy-expired")
    admin = AdminPrincipal(
        email="policy-expired-admin@example.test",
        display_name="Policy Admin",
        password_hash="not-a-real-password-hash",
        role="super_admin",
    )
    db_session.add(admin)
    await db_session.flush()
    now = datetime.now(timezone.utc)
    expired = TenantDataUsePolicy(
        tenant_id=tenant.id, mode="shared_training",
        contract_reference="contract-old", contract_version="v1",
        effective_at=now - timedelta(days=10),
        expires_at=now - timedelta(days=1),
        approved_by_admin_id=admin.id,
        evidence_reference="test-evidence://expired",
    )
    revoked = TenantDataUsePolicy(
        tenant_id=tenant.id, mode="shared_training",
        contract_reference="contract-revoked", contract_version="v1",
        effective_at=now - timedelta(days=2),
        revoked_at=now - timedelta(hours=1),
        approved_by_admin_id=admin.id,
        evidence_reference="test-evidence://revoked",
    )
    db_session.add_all([expired, revoked])
    await db_session.commit()

    decision = await resolve_training_policy(
        db_session, tenant_id=tenant.id, purpose="shared_base_training",
        dataset_eligible=True, now=now,
    )
    assert not decision.alloweded


@pytest.mark.asyncio
async def test_policy_requires_approval_and_evidence(db_session, tenant_factory):
    tenant, _ = await tenant_factory(slug="policy-unapproved")
    policy = TenantDataUsePolicy(
        tenant_id=tenant.id, mode="shared_training",
        contract_reference="contract-003", contract_version="v1",
        effective_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        evidence_reference=None,
    )
    db_session.add(policy)
    await db_session.commit()

    decision = await resolve_training_policy(
        db_session, tenant_id=tenant.id, purpose="shared_base_training",
        dataset_eligible=True,
    )
    assert not decision.allowed
    assert "approval" in decision.reason.lower()


@pytest.mark.asyncio
async def test_newer_revocation_never_falls_back_to_older_authorization(db_session, tenant_factory):
    tenant, _ = await tenant_factory(slug="policy-revocation-wins")
    admin = AdminPrincipal(
        email="policy-revocation-admin@example.test",
        display_name="Policy Admin",
        password_hash="not-a-real-password-hash",
        role="super_admin",
    )
    db_session.add(admin)
    await db_session.flush()
    now = datetime.now(timezone.utc)
    previously_authorized = TenantDataUsePolicy(
        tenant_id=tenant.id, mode="shared_training",
        contract_reference="contract-previous", contract_version="v1",
        effective_at=now - timedelta(days=5),
        approved_by_admin_id=admin.id,
        evidence_reference="test-evidence://previous",
    )
    later_revocation = TenantDataUsePolicy(
        tenant_id=tenant.id, mode="shared_training",
        contract_reference="contract-revoked", contract_version="v2",
        effective_at=now - timedelta(days=1),
        revoked_at=now - timedelta(hours=1),
        approved_by_admin_id=admin.id,
        evidence_reference="test-evidence://revocation",
    )
    db_session.add_all([previously_authorized, later_revocation])
    await db_session.commit()

    decision = await resolve_training_policy(
        db_session, tenant_id=tenant.id, purpose="shared_base_training",
        dataset_eligible=True, now=now,
    )
    assert not decision.allowed
    assert decision.policy_id == later_revocation.id
    assert "revoked" in decision.reason.lower()


@pytest.mark.asyncio
@pytest.mark.parametrize("policy_state", ["expired", "revoked", "unapproved"])
async def test_sharing_policy_state_does_not_replace_local_authorization(
    db_session, tenant_factory, policy_state
):
    tenant, _ = await tenant_factory(slug=f"local-auth-{policy_state}")
    admin = AdminPrincipal(
        email=f"local-auth-{policy_state}@example.test",
        display_name="Policy Admin",
        password_hash="not-a-real-password-hash",
        role="super_admin",
    )
    db_session.add(admin)
    await db_session.flush()
    now = datetime.now(timezone.utc)
    kwargs = {
        "tenant_id": tenant.id,
        "mode": "shared_training",
        "contract_reference": "contract-local-auth",
        "contract_version": "v1",
        "effective_at": now - timedelta(days=5),
        "evidence_reference": "test-evidence://local-auth",
        "approved_by_admin_id": admin.id,
    }
    if policy_state == "expired":
        kwargs["expires_at"] = now - timedelta(days=1)
    elif policy_state == "revoked":
        kwargs["revoked_at"] = now - timedelta(hours=1)
    elif policy_state == "unapproved":
        kwargs["approved_by_admin_id"] = None
        kwargs["evidence_reference"] = None
    db_session.add(TenantDataUsePolicy(**kwargs))
    await db_session.commit()

    shared = await resolve_training_policy(
        db_session, tenant_id=tenant.id, purpose="shared_base_training",
        dataset_eligible=True, now=now,
    )
    local_without_authorization = await resolve_training_policy(
        db_session, tenant_id=tenant.id, purpose="institutional_training",
        dataset_eligible=True, now=now,
    )
    local_with_authorization = await resolve_training_policy(
        db_session, tenant_id=tenant.id, purpose="institutional_training",
        dataset_eligible=True, institutional_use_authorized=True, now=now,
    )
    assert not shared.allowed
    assert not local_without_authorization.allowed
    assert local_with_authorization.allowed
