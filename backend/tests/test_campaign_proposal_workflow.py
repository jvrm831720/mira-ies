from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.core.auth import AuthContext, get_current_tenant
from app.models.auth import User
from app.models.retention_campaign import RetentionCampaignProposal, RetentionCampaignProposalAuditEvent


def _proposal(tenant_id: str, creator_id: str) -> RetentionCampaignProposal:
    return RetentionCampaignProposal(
        tenant_id=tenant_id,
        status="draft",
        title="Proposta de retenção",
        source_group_ids=["risk_critical"],
        source_catalog_version="test-v1",
        recommendation_engine="signals-and-rules-v1",
        source_evaluated_at=datetime.now(timezone.utc),
        objective="Reduzir risco de evasão",
        strategy="Contato consultivo",
        recommended_channels=["email"],
        cadence_days=[0, 3],
        message_brief="Mensagem a revisar",
        audience_snapshot=[{
            "student_id": "student-internal-id",
            "matched_group_ids": ["risk_critical"],
            "eligible_channels": ["email"],
            "blocked_reasons": [],
            "internal_action_only": False,
        }],
        audience_hash="a" * 64,
        audience_total=1,
        outreach_eligible_count=1,
        blocked_count=0,
        internal_action_count=0,
        created_by=creator_id,
    )


def _user(tenant_id: str, name: str, email: str, role: str) -> User:
    return User(
        tenant_id=tenant_id,
        display_name=name,
        email=email,
        password_hash="not-a-real-hash",
        role=role,
        is_active=True,
        mfa_enabled_at=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_proposal_review_attestation_and_approval_are_audited(client, tenant, db_session):
    from app.main import app

    institution, _api_key = tenant
    creator = _user(institution.id, "Campaign Creator", f"creator-{institution.id}@example.test", "coordinator")
    reviewer = _user(institution.id, "Campaign Reviewer", f"reviewer-{institution.id}@example.test", "coordinator")
    approver = _user(institution.id, "Campaign Approver", f"approver-{institution.id}@example.test", "admin")
    db_session.add_all([creator, reviewer, approver])
    await db_session.flush()
    proposal = _proposal(institution.id, creator.id)
    db_session.add(proposal)
    await db_session.commit()
    await db_session.refresh(proposal)
    original_snapshot = proposal.audience_snapshot
    original_hash = proposal.audience_hash

    current_auth = {"value": AuthContext(
        tenant=institution, tenant_id=institution.id, tenant_slug=institution.slug,
        user_id=reviewer.id, role="coordinator", aal=2,
    )}
    app.dependency_overrides[get_current_tenant] = lambda: current_auth["value"]
    try:
        response = await client.post(
            f"/api/v1/agents/retention/campaigns/intelligence/proposals/{proposal.id}/review"
        )
        assert response.status_code == 200
        assert response.json()["status"] == "in_review"

        current_auth["value"] = AuthContext(
            tenant=institution, tenant_id=institution.id, tenant_slug=institution.slug,
            user_id=approver.id, role="admin", aal=2,
        )
        response = await client.post(
            f"/api/v1/agents/retention/campaigns/intelligence/proposals/{proposal.id}/authorization-attestation",
            json={
                "basis": "Autorização institucional registrada",
                "evidence_reference": "contract-ref-2026-01",
                "attestation": True,
            },
        )
        assert response.status_code == 200
        assert response.json()["authorization_status"] == "institution_attested"

        response = await client.post(
            f"/api/v1/agents/retention/campaigns/intelligence/proposals/{proposal.id}/approve"
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "approved"
        assert payload["execution_enabled"] is False
        assert payload["audience_snapshot"] == original_snapshot
        assert payload["audience_hash"] == original_hash

        response = await client.patch(
            f"/api/v1/agents/retention/campaigns/intelligence/proposals/{proposal.id}",
            json={"title": "Tentativa após aprovação"},
        )
        assert response.status_code == 409

        audit = await db_session.execute(
            select(RetentionCampaignProposalAuditEvent)
            .where(RetentionCampaignProposalAuditEvent.proposal_id == proposal.id)
            .order_by(RetentionCampaignProposalAuditEvent.created_at)
        )
        events = list(audit.scalars().all())
        assert [event.event_type for event in events] == [
            "proposal.submitted_for_review",
            "proposal.communication_authorization_attested",
            "proposal.approved",
        ]
    finally:
        app.dependency_overrides.pop(get_current_tenant, None)


@pytest.mark.asyncio
async def test_creator_cannot_submit_own_proposal_for_review(client, tenant, db_session):
    from app.main import app

    institution, _api_key = tenant
    creator = _user(institution.id, "Same Person", f"same-{institution.id}@example.test", "coordinator")
    db_session.add(creator)
    await db_session.flush()
    proposal = _proposal(institution.id, creator.id)
    db_session.add(proposal)
    await db_session.commit()
    await db_session.refresh(proposal)
    app.dependency_overrides[get_current_tenant] = lambda: AuthContext(
        tenant=institution, tenant_id=institution.id, tenant_slug=institution.slug,
        user_id=creator.id, role="coordinator", aal=2,
    )
    try:
        response = await client.post(
            f"/api/v1/agents/retention/campaigns/intelligence/proposals/{proposal.id}/review"
        )
        assert response.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_tenant, None)


@pytest.mark.asyncio
async def test_edit_changes_content_but_preserves_audience_snapshot(client, tenant, db_session):
    from app.main import app

    institution, _api_key = tenant
    creator = _user(institution.id, "Creator", f"editor-{institution.id}@example.test", "coordinator")
    db_session.add(creator)
    await db_session.flush()
    proposal = _proposal(institution.id, creator.id)
    db_session.add(proposal)
    await db_session.commit()
    await db_session.refresh(proposal)
    original_snapshot = proposal.audience_snapshot
    original_hash = proposal.audience_hash
    app.dependency_overrides[get_current_tenant] = lambda: AuthContext(
        tenant=institution, tenant_id=institution.id, tenant_slug=institution.slug,
        user_id=creator.id, role="coordinator", aal=2,
    )
    try:
        response = await client.patch(
            f"/api/v1/agents/retention/campaigns/intelligence/proposals/{proposal.id}",
            json={"title": "Título revisado", "cadence_days": [0, 5, 10]},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["title"] == "Título revisado"
        assert payload["revision"] == 2
        assert payload["audience_snapshot"] == original_snapshot
        assert payload["audience_hash"] == original_hash
    finally:
        app.dependency_overrides.pop(get_current_tenant, None)
