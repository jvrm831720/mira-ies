from datetime import datetime, timedelta, timezone

import pytest

from app.models.control_center import AdminPrincipal
from app.models.institutional_training_authorization import InstitutionalTrainingAuthorization
from app.services.training_policy import resolve_institutional_training_authorization


@pytest.mark.asyncio
async def test_institutional_training_authorization_missing_denies(db_session, tenant_factory):
    tenant, _ = await tenant_factory(slug="institutional-auth-missing")
    decision = await resolve_institutional_training_authorization(
        db_session, tenant_id=tenant.id
    )
    assert not decision.allowed
    assert decision.authorization_id is None


@pytest.mark.asyncio
async def test_current_separately_approved_authorization_allows(db_session, tenant_factory):
    tenant, _ = await tenant_factory(slug="institutional-auth-valid")
    admin = AdminPrincipal(
        email="institutional-auth-admin@example.test",
        display_name="Authorization Admin",
        password_hash="not-a-real-password-hash",
        role="super_admin",
    )
    db_session.add(admin)
    await db_session.flush()
    record = InstitutionalTrainingAuthorization(
        tenant_id=tenant.id,
        contract_reference="local-training-contract-001",
        contract_version="v1",
        effective_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        approved_by_admin_id=admin.id,
        evidence_reference="test-evidence://local-training-contract-001",
    )
    db_session.add(record)
    await db_session.commit()

    decision = await resolve_institutional_training_authorization(
        db_session, tenant_id=tenant.id
    )
    assert decision.allowed
    assert decision.authorization_id == record.id


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["expired", "revoked", "unapproved"])
async def test_latest_invalid_authorization_never_revives_older_record(
    db_session, tenant_factory, state
):
    tenant, _ = await tenant_factory(slug=f"institutional-auth-{state}")
    admin = AdminPrincipal(
        email=f"institutional-auth-{state}@example.test",
        display_name="Authorization Admin",
        password_hash="not-a-real-password-hash",
        role="super_admin",
    )
    db_session.add(admin)
    await db_session.flush()
    now = datetime.now(timezone.utc)
    older = InstitutionalTrainingAuthorization(
        tenant_id=tenant.id,
        contract_reference="local-training-contract-old",
        contract_version="v1",
        effective_at=now - timedelta(days=5),
        approved_by_admin_id=admin.id,
        evidence_reference="test-evidence://old",
    )
    latest_values = {
        "tenant_id": tenant.id,
        "contract_reference": "local-training-contract-new",
        "contract_version": "v2",
        "effective_at": now - timedelta(days=1),
        "approved_by_admin_id": admin.id,
        "evidence_reference": "test-evidence://new",
    }
    if state == "expired":
        latest_values["expires_at"] = now - timedelta(hours=1)
    elif state == "revoked":
        latest_values["revoked_at"] = now - timedelta(minutes=1)
    else:
        latest_values["approved_by_admin_id"] = None
        latest_values["evidence_reference"] = None
    latest = InstitutionalTrainingAuthorization(**latest_values)
    db_session.add_all([older, latest])
    await db_session.commit()

    decision = await resolve_institutional_training_authorization(
        db_session, tenant_id=tenant.id, now=now
    )
    assert not decision.allowed
    assert decision.authorization_id == latest.id


@pytest.mark.asyncio
async def test_training_pipeline_blocks_before_readiness_refresh_without_authorization(
    db_session, tenant_factory, monkeypatch
):
    from app.ml import tenant_train

    tenant, _ = await tenant_factory(slug="pipeline-auth-blocked")

    async def unexpected_readiness_refresh(*args, **kwargs):
        raise AssertionError("readiness refresh must not run before authorization")

    monkeypatch.setattr(
        tenant_train, "refresh_tenant_readiness", unexpected_readiness_refresh
    )
    with pytest.raises(ValueError, match="Treino institucional bloqueado por governanca"):
        await tenant_train.train_tenant_model(db_session, tenant_slug=tenant.slug)
