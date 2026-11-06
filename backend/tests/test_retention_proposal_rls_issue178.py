"""Regression for Issue #178: proposal rows must never cross tenants."""

from datetime import datetime, timezone
import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.models.retention_campaign import RetentionCampaignProposal


def _proposal(tenant_id: str, suffix: str) -> RetentionCampaignProposal:
    return RetentionCampaignProposal(
        tenant_id=tenant_id,
        status="draft",
        title=f"Proposal {suffix}",
        source_group_ids=[],
        source_catalog_version="test",
        recommendation_engine="test",
        source_evaluated_at=datetime.now(timezone.utc),
        objective="Test tenant isolation",
        strategy="No actual outreach",
        recommended_channels=[],
        cadence_days=[],
        message_brief="Never send",
        audience_snapshot=[],
        audience_hash="0" * 64,
        audience_total=0,
        outreach_eligible_count=0,
        blocked_count=0,
        internal_action_count=0,
    )


@pytest.mark.asyncio
async def test_retention_proposal_rls_enforces_tenant_for_read_write(
    db_session, tenant_factory
):
    bypass = (await db_session.execute(text(
        "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user"
    ))).scalar_one()
    assert bypass is False, "RLS tests must use an unprivileged database role."

    # ORM fixture recreates SQLAlchemy tables; recreate the migration's policy
    # here to validate its behavior on the non-superuser integration role.
    await db_session.execute(text(
        "ALTER TABLE retention_campaign_proposals ENABLE ROW LEVEL SECURITY"
    ))
    await db_session.execute(text(
        "ALTER TABLE retention_campaign_proposals FORCE ROW LEVEL SECURITY"
    ))
    await db_session.execute(text(
        "DROP POLICY IF EXISTS retention_proposals_tenant_isolation "
        "ON retention_campaign_proposals"
    ))
    await db_session.execute(text("""
        CREATE POLICY retention_proposals_tenant_isolation
        ON retention_campaign_proposals FOR ALL
        USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    """))
    await db_session.commit()

    tenant_a, _ = await tenant_factory(slug="proposal-rls-178-a")
    tenant_b, _ = await tenant_factory(slug="proposal-rls-178-b")
    tenant_a_id, tenant_b_id = tenant_a.id, tenant_b.id

    async def context(tenant_id: str) -> None:
        await db_session.execute(
            text("SELECT set_config('app.tenant_id', :id, true)"),
            {"id": tenant_id},
        )

    await context(tenant_a_id)
    row_a = _proposal(tenant_a_id, "a")
    db_session.add(row_a)
    await db_session.flush()
    row_a_id = row_a.id
    await db_session.commit()

    await context(tenant_b_id)
    row_b = _proposal(tenant_b_id, "b")
    db_session.add(row_b)
    await db_session.flush()
    row_b_id = row_b.id
    await db_session.commit()

    await context(tenant_a_id)
    visible_a = (await db_session.execute(
        select(RetentionCampaignProposal.id)
    )).scalars().all()
    assert visible_a == [row_a_id]
    changed = await db_session.execute(text(
        "UPDATE retention_campaign_proposals SET title='unauthorized' WHERE id=:id"
    ), {"id": row_b_id})
    assert changed.rowcount == 0
    await db_session.rollback()

    await context(tenant_b_id)
    visible_b = (await db_session.execute(
        select(RetentionCampaignProposal.id)
    )).scalars().all()
    assert visible_b == [row_b_id]
    await db_session.rollback()

    await context(tenant_a_id)
    db_session.add(_proposal(tenant_b_id, "foreign"))
    with pytest.raises(DBAPIError):
        await db_session.flush()
    await db_session.rollback()

    await context("")
    assert (await db_session.execute(
        select(RetentionCampaignProposal.id)
    )).scalars().all() == []
    await db_session.rollback()
