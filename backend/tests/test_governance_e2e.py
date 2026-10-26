from datetime import datetime, timedelta, timezone

import pytest
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.auth import AuthContext, get_current_tenant
from app.main import app
from app.ml.targets import TARGET_DEFINITION_VERSION
from app.models.control_center import AdminPrincipal
from app.models.data_governance import TenantDataUsePolicy
from app.models.tenant import ModelArtifact, Tenant
from app.services.training_policy import resolve_training_policy


def _policy(tenant_id, mode, admin_id, effective_at, suffix):
    return TenantDataUsePolicy(
        tenant_id=tenant_id,
        mode=mode,
        contract_reference=f"contract-{suffix}",
        contract_version="v1",
        effective_at=effective_at,
        approved_by_admin_id=admin_id,
        evidence_reference=f"test-evidence://{suffix}",
    )


@pytest.mark.asyncio
async def test_two_tenants_are_isolated_and_share_only_when_individually_authorized(
    db_session, tenant_factory
):
    tenant_a, _ = await tenant_factory(slug="e2e-tenant-a", name="Tenant A")
    tenant_b, _ = await tenant_factory(slug="e2e-tenant-b", name="Tenant B")
    admin = AdminPrincipal(
        email="e2e-governance-admin@example.test",
        display_name="E2E Governance Admin",
        password_hash="not-a-real-password-hash",
        role="super_admin",
    )
    db_session.add(admin)
    await db_session.flush()
    now = datetime.now(timezone.utc)
    db_session.add_all([
        _policy(tenant_a.id, "shared_training", admin.id, now - timedelta(minutes=2), "tenant-a-shared"),
        _policy(tenant_b.id, "institution_only", admin.id, now - timedelta(minutes=2), "tenant-b-private"),
    ])
    await db_session.commit()

    a_shared = await resolve_training_policy(
        db_session, tenant_id=tenant_a.id, purpose="shared_base_training", dataset_eligible=True, now=now
    )
    b_shared = await resolve_training_policy(
        db_session, tenant_id=tenant_b.id, purpose="shared_base_training", dataset_eligible=True, now=now
    )
    b_local = await resolve_training_policy(
        db_session, tenant_id=tenant_b.id, purpose="institutional_training",
        dataset_eligible=True, institutional_use_authorized=True, now=now,
    )

    assert a_shared.allowed is True
    assert a_shared.tenant_id == tenant_a.id
    assert b_shared.allowed is False
    assert b_shared.tenant_id == tenant_b.id
    assert b_local.allowed is True


@pytest.mark.asyncio
async def test_switch_from_shared_to_private_blocks_future_shared_contributions(
    db_session, tenant_factory
):
    tenant, _ = await tenant_factory(slug="e2e-mode-transition")
    admin = AdminPrincipal(
        email="e2e-transition-admin@example.test",
        display_name="E2E Transition Admin",
        password_hash="not-a-real-password-hash",
        role="super_admin",
    )
    db_session.add(admin)
    await db_session.flush()
    now = datetime.now(timezone.utc)
    db_session.add(_policy(tenant.id, "shared_training", admin.id, now - timedelta(days=2), "before-switch"))
    await db_session.flush()

    before = await resolve_training_policy(
        db_session, tenant_id=tenant.id, purpose="shared_base_training", dataset_eligible=True, now=now
    )
    db_session.add(_policy(tenant.id, "institution_only", admin.id, now - timedelta(seconds=1), "after-switch"))
    await db_session.commit()

    after = await resolve_training_policy(
        db_session, tenant_id=tenant.id, purpose="shared_base_training", dataset_eligible=True, now=now
    )
    local = await resolve_training_policy(
        db_session, tenant_id=tenant.id, purpose="institutional_training",
        dataset_eligible=True, institutional_use_authorized=True, now=now,
    )
    assert before.allowed is True
    assert after.allowed is False
    assert after.mode == "institution_only"
    assert local.allowed is True


@pytest.mark.asyncio
async def test_model_activation_rollback_and_cross_tenant_artifact_access(
    client, db_session, tenant_factory
):
    tenant_a, _ = await tenant_factory(slug="e2e-model-tenant-a", name="Model Tenant A")
    tenant_b, _ = await tenant_factory(slug="e2e-model-tenant-b", name="Model Tenant B")
    old = ModelArtifact(
        tenant_id=tenant_a.id, name="tenant-a-model", version="1.0.0", scope="tenant",
        storage_path="/test-only/tenant-a-v1.joblib",
        metrics={"target_definition": TARGET_DEFINITION_VERSION, "fixture": True},
        is_active=True, lifecycle_status="active", trained_at=datetime.now(timezone.utc),
    )
    candidate_a = ModelArtifact(
        tenant_id=tenant_a.id, name="tenant-a-model", version="2.0.0", scope="tenant",
        storage_path="/test-only/tenant-a-v2.joblib",
        metrics={"target_definition": TARGET_DEFINITION_VERSION, "fixture": True},
        is_active=False, lifecycle_status="candidate", trained_at=datetime.now(timezone.utc),
    )
    candidate_b = ModelArtifact(
        tenant_id=tenant_b.id, name="tenant-b-model", version="1.0.0", scope="tenant",
        storage_path="/test-only/tenant-b-v1.joblib",
        metrics={"target_definition": TARGET_DEFINITION_VERSION, "fixture": True},
        is_active=False, lifecycle_status="candidate", trained_at=datetime.now(timezone.utc),
    )
    db_session.add_all([old, candidate_a, candidate_b])
    await db_session.flush()
    tenant_a.active_model_id = old.id
    await db_session.commit()
    await db_session.refresh(old)
    await db_session.refresh(candidate_a)
    await db_session.refresh(candidate_b)

    async def _tenant_a_auth(db: AsyncSession = Depends(get_db)):
        api_tenant = await db.get(Tenant, tenant_a.id)
        return AuthContext(
            tenant=api_tenant, tenant_id=tenant_a.id, tenant_slug=tenant_a.slug,
            user_id="00000000-0000-4000-8000-000000000001", role="admin",
        )

    app.dependency_overrides[get_current_tenant] = _tenant_a_auth
    try:
        # A tenant-A session cannot address tenant B's model, even with its exact artifact ID.
        foreign = await client.post(
            f"/api/v1/tenants/{tenant_a.slug}/models/{candidate_b.id}/approve",
            json={"reason": "test cross-tenant access rejection"},
        )
        assert foreign.status_code == 404

        approved = await client.post(
            f"/api/v1/tenants/{tenant_a.slug}/models/{candidate_a.id}/approve",
            json={"reason": "e2e approved after evaluation"},
        )
        assert approved.status_code == 200
        activated = await client.post(
            f"/api/v1/tenants/{tenant_a.slug}/models/{candidate_a.id}/activate",
            json={"reason": "e2e activation"},
        )
        assert activated.status_code == 200
        assert activated.json()["version"] == "2.0.0"

        rolled_back = await client.post(
            f"/api/v1/tenants/{tenant_a.slug}/models/{old.id}/rollback",
            json={"reason": "e2e recovery after regression"},
        )
        assert rolled_back.status_code == 200
        assert rolled_back.json()["status"] == "rolled_back"
        assert rolled_back.json()["rolled_back_from_artifact_id"] == candidate_a.id
    finally:
        app.dependency_overrides.pop(get_current_tenant, None)

    await db_session.refresh(old)
    await db_session.refresh(candidate_a)
    assert old.is_active is True
    assert old.lifecycle_status == "active"
    assert candidate_a.is_active is False
    assert candidate_a.lifecycle_status == "retired"
    assert old.rollback_of_artifact_id == candidate_a.id


@pytest.mark.asyncio
async def test_single_prediction_returns_exact_model_version(client, auth_headers, monkeypatch):
    from app.api import scoring as scoring_api

    monkeypatch.setattr(scoring_api, "get_model_info", lambda: {"status": "ready", "version": "base-test-v7"})
    monkeypatch.setattr(scoring_api, "score_student_dict", lambda _payload: {
        "risk_score": 42.0, "model_score": 40.0, "risk_level": "medio", "probability": 0.42,
        "shap_top_factors": [], "shap_summary": "test", "features_used": {},
    })
    response = await client.post("/api/v1/predict", headers=auth_headers, json={})
    assert response.status_code == 200
    assert response.json()["model_scope"] == "base"
    assert response.json()["model_version"] == "base-test-v7"


@pytest.mark.asyncio
async def test_single_prediction_fails_closed_when_model_version_is_missing(client, auth_headers, monkeypatch):
    from app.api import scoring as scoring_api

    monkeypatch.setattr(scoring_api, "get_model_info", lambda: {"status": "error"})
    response = await client.post("/api/v1/predict", headers=auth_headers, json={})
    assert response.status_code == 503
