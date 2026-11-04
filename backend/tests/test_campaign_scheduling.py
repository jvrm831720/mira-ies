from datetime import datetime, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from app.core.auth import AuthContext, get_current_tenant
from app.models.retention_campaign import (
    RetentionCampaignProposal,
    RetentionCampaignProposalAuditEvent,
)


def _approved_proposal(tenant_id: str, creator_id: str):
    return RetentionCampaignProposal(
        tenant_id=tenant_id,
        status="approved",
        title="Campanha agendada",
        source_group_ids=["risk_critical"],
        source_catalog_version="test-v1",
        recommendation_engine="signals-and-rules-v1",
        source_evaluated_at=datetime.now(timezone.utc),
        objective="Reduzir risco de evasão",
        strategy="Contato consultivo",
        recommended_channels=["email"],
        cadence_days=[0, 3],
        message_brief="Mensagem revisada",
        audience_snapshot=[],
        audience_hash="a" * 64,
        audience_total=0,
        outreach_eligible_count=0,
        blocked_count=0,
        internal_action_count=0,
        created_by=creator_id,
        authorization_status="institution_attested",
        authorization_basis="Contrato institucional",
        authorization_reference="contract-ref",
        authorization_attested_by="institution-admin",
        authorization_attested_at=datetime.now(timezone.utc),
    )


def _admin_auth(institution, admin_id):
    return AuthContext(
        tenant=institution,
        tenant_id=institution.id,
        tenant_slug=institution.slug,
        user_id=admin_id,
        role="admin",
        aal=2,
    )


@pytest.mark.asyncio
async def test_schedule_and_remove_schedule_are_tenant_scoped_and_audited(
    client, tenant, tenant_factory, db_session
):
    from app.main import app

    institution, _ = tenant
    proposal = _approved_proposal(institution.id, "creator")
    db_session.add(proposal)
    await db_session.commit()
    await db_session.refresh(proposal)
    other_tenant, _ = await tenant_factory(slug="other-tenant")
    other_proposal = _approved_proposal(other_tenant.id, "other-creator")
    db_session.add(other_proposal)
    await db_session.commit()
    await db_session.refresh(other_proposal)
    app.dependency_overrides[get_current_tenant] = lambda: _admin_auth(
        institution, str(uuid4())
    )
    try:
        future = (datetime.now(ZoneInfo("America/Sao_Paulo")) + timedelta(days=2)).replace(microsecond=0)
        cross_tenant = await client.post(
            f"/api/v1/agents/retention/campaigns/intelligence/proposals/{other_proposal.id}/schedule",
            json={
                "scheduled_for": future.isoformat(),
                "schedule_timezone": "America/Sao_Paulo",
            },
        )
        assert cross_tenant.status_code == 404
        response = await client.post(
            f"/api/v1/agents/retention/campaigns/intelligence/proposals/{proposal.id}/schedule",
            json={
                "scheduled_for": future.isoformat(),
                "schedule_timezone": "America/Sao_Paulo",
            },
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["status"] == "scheduled"
        assert payload["schedule_timezone"] == "America/Sao_Paulo"
        assert payload["execution_enabled"] is False
        assert payload["dispatch_created"] is False

        listing = await client.get(
            "/api/v1/agents/retention/campaigns/intelligence/schedule"
        )
        assert listing.status_code == 200
        assert listing.json()["count"] == 1

        response = await client.delete(
            f"/api/v1/agents/retention/campaigns/intelligence/proposals/{proposal.id}/schedule"
        )
        assert response.status_code == 200
        assert response.json()["status"] == "approved"
        assert response.json()["scheduled_for"] is None

        events = list((await db_session.execute(
            select(RetentionCampaignProposalAuditEvent)
            .where(RetentionCampaignProposalAuditEvent.proposal_id == proposal.id)
            .order_by(RetentionCampaignProposalAuditEvent.created_at)
        )).scalars().all())
        assert [event.event_type for event in events] == [
            "proposal.scheduled",
            "proposal.schedule_removed",
        ]
    finally:
        app.dependency_overrides.pop(get_current_tenant, None)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("schedule_value", "zone", "expected_detail"),
    [
        ("2030-01-01T12:00:00", "America/Sao_Paulo", "offset UTC explícito"),
        ("2030-01-01T12:00:00-03:00", "Mars/Olympus", "Fuso IANA desconhecido"),
        ("2030-01-01T12:00:00+00:00", "America/Sao_Paulo", "offset informado"),
        ("2000-01-01T12:00:00-03:00", "America/Sao_Paulo", "no futuro"),
    ],
)
async def test_schedule_rejects_invalid_datetime_or_timezone(
    client, tenant, db_session, schedule_value, zone, expected_detail
):
    from app.main import app

    institution, _ = tenant
    proposal = _approved_proposal(institution.id, "creator")
    db_session.add(proposal)
    await db_session.commit()
    await db_session.refresh(proposal)
    app.dependency_overrides[get_current_tenant] = lambda: _admin_auth(
        institution, "scheduler-admin"
    )
    try:
        response = await client.post(
            f"/api/v1/agents/retention/campaigns/intelligence/proposals/{proposal.id}/schedule",
            json={"scheduled_for": schedule_value, "schedule_timezone": zone},
        )
        assert response.status_code == 422
        assert expected_detail in response.text
    finally:
        app.dependency_overrides.pop(get_current_tenant, None)


@pytest.mark.asyncio
async def test_only_approved_proposals_can_be_scheduled(client, tenant, db_session):
    from app.main import app

    institution, _ = tenant
    proposal = _approved_proposal(institution.id, "creator")
    proposal.status = "draft"
    db_session.add(proposal)
    await db_session.commit()
    await db_session.refresh(proposal)
    app.dependency_overrides[get_current_tenant] = lambda: _admin_auth(
        institution, "scheduler-admin"
    )
    try:
        future = (datetime.now(ZoneInfo("America/Sao_Paulo")) + timedelta(days=1)).isoformat()
        response = await client.post(
            f"/api/v1/agents/retention/campaigns/intelligence/proposals/{proposal.id}/schedule",
            json={
                "scheduled_for": future,
                "schedule_timezone": "America/Sao_Paulo",
            },
        )
        assert response.status_code == 409
        assert "aprovadas" in response.text
    finally:
        app.dependency_overrides.pop(get_current_tenant, None)
