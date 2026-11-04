from datetime import datetime, timezone

import pytest

from app.core.auth import AuthContext, get_current_tenant
from app.models.auth import User
from app.models.retention_campaign import RetentionCampaignProposal, RetentionCampaignProposalAuditEvent


@pytest.mark.asyncio
async def test_proposal_review_attestation_and_approval_are_audited(
    client, tenant, db_session
):
    from app.main import app

    from app.main import app

    institution, _api_key = tenant
    creator = User(
        tenant_id=institution.id,
        display_name="Campaign Creator",
        email=f"creator-{institution.id}@example.test",
        password_hash="not-a-real-hash",
        role="coordinator",
        is_active=True,
        mfa_enabled_at=datetime.now(timezone.utc),
    )
    reviewer = User(
        tenant_id=institution.id,
        display_name="Campaign Reviewer",
        email=f"reviewer-{institution.id}@example.test",
        password_hash="not-a-real-hash",
        role="coordinator",
        is_active=True,
        mfa_enabled_at=datetime.now(timezone.utc),
    )
    approver = User(
        tenant_id=institution.id,
        display_name="Campaign Approver",
        email=f"approver-{institution.id}@example.test",
        password_hash="not-a-real-hash",
        role="admin",
        is_active=True,
        mfa_enabled_at=datetime.now(timezone.utc),
    )
    db_session.add_all([creator, reviewer, approver])
    await db_session.flush()
    proposal = RetentionCampaignProposal(
        tenant_id=institution.id,
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
        created_by=creator.id,
    )
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
            __import__("sqlalchemy").select(RetentionCampaignProposalAuditEvent)
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
        client._transport.app.dependency_overrides.pop(get_current_tenant, None)


@pytest.mark.asyncio
async def test_creator_cannot_submit_own_proposal_for_review(client, tenant, db_session):
    institution, _api_key = tenant
    creator = User(
        tenant_id=institution.id,
        display_name="Same Person",
        email=f"same-{institution.id}@example.test",
        password_hash="not-a-real-hash",
        role="coordinator",
        is_active=True,
        mfa_enabled_at=datetime.now(timezone.utc),
    )
    db_session.add(creator)
    await db_session.flush()
    proposal = RetentionCampaignProposal(
        tenant_id=institution.id,
        status="draft",
        title="Proposta",
        source_group_ids=["risk_critical"],
        source_catalog_version="test-v1",
        recommendation_engine="signals-and-rules-v1",
        source_evaluated_at=datetime.now(timezone.utc),
        objective="Objetivo",
        strategy="Estratégia",
        recommended_channels=["email"],
        cadence_days=[0],
        message_brief="Briefing",
        audience_snapshot=[{"student_id": "s1"}],
        audience_hash="b" * 64,
        audience_total=1,
        outreach_eligible_count=1,
        blocked_count=0,
        internal_action_count=0,
        created_by=creator.id,
    )
    db_session.add(proposal)
    await db_session.commit()
    await db_session.refresh(proposal)
    client._transport.app.dependency_overrides[get_current_tenant] = lambda: AuthContext(
        tenant=institution, tenant_id=institution.id, tenant_slug=institution.slug,
        user_id=creator.id, role="coordinator", aal=2,
    )
    try:
        response = await client.post(
            f"/api/v1/agents/retention/campaigns/intelligence/proposals/{proposal.id}/review"
        )
        assert response.status_code == 403
    finally:
        client._transport.app.dependency_overrides.pop(get_current_tenant, None)
