"""Real signed MFA session -> group-based retention campaign proposal -> tenant-scoped read.

Exercises the actual ASGI auth middleware, PostgreSQL evaluation and persistence.
No provider is called and no campaign is scheduled, approved or sent.
"""
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.core.mira_security import hash_password
from app.core.user_sessions import create_user_session
from app.models.auth import User
from app.models.student import Student, UploadBatch


@pytest.mark.asyncio
async def test_authenticated_campaign_proposal_creation_and_tenant_isolation(
    client, db_session, tenant_factory
):
    tenant_a, _ = await tenant_factory(slug="campaign-e2e-a")
    tenant_b, _ = await tenant_factory(slug="campaign-e2e-b")

    for tenant, prefix in ((tenant_a, "OWN"), (tenant_b, "FOREIGN")):
        batch = UploadBatch(
            tenant_id=tenant.id, filename=prefix + ".csv", original_filename=prefix + ".csv",
            status="processed",
        )
        db_session.add(batch)
        await db_session.flush()
        db_session.add(Student(
            tenant_id=tenant.id, batch_id=batch.id, matricula=prefix + "-" + str(uuid4()),
            nome="Aluno " + prefix, curso="Engenharia", is_active=True,
            risk_score=94.0, risk_level="critico",
            email=prefix.lower() + "@example.test", telefone="+5521999988877",
            communication_opt_out=False,
        ))
    user = User(
        tenant_id=tenant_a.id, display_name="Gestora de permanência",
        email="campaign-human-e2e@example.test",
        password_hash=hash_password("CampaignTest!2026"),
        role="coordinator", is_active=True,
        mfa_enabled_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    token, _ = await create_user_session(db_session, user, tenant_a, aal=2)
    await db_session.commit()

    headers = {"Authorization": "Bearer " + token}
    me = await client.get("/api/v1/org/me", headers=headers)
    assert me.status_code == 200, me.text
    assert me.json()["tenant_id"] == tenant_a.id

    created = await client.post(
        "/api/v1/agents/retention/campaigns/intelligence/proposals",
        headers=headers, json={"group_ids": ["risk_critical"]},
    )
    assert created.status_code == 201, created.text
    proposal = created.json()
    assert proposal["tenant_id"] == tenant_a.id
    assert proposal["status"] == "draft"
    assert proposal["source_group_ids"] == ["risk_critical"]
    assert proposal["audience_total"] == 1
    assert proposal["audience_snapshot"][0]["matched_group_ids"] == ["risk_critical"]
    assert proposal["execution_enabled"] is False
    assert proposal["authorization_status"] != "institution_attested"

    listing = await client.get(
        "/api/v1/agents/retention/campaigns/intelligence/proposals",
        headers=headers,
    )
    assert listing.status_code == 200, listing.text
    assert [p["id"] for p in listing.json()["proposals"]] == [proposal["id"]]

    foreign_user = User(
        tenant_id=tenant_b.id, display_name="Outro workspace",
        email="campaign-foreign-e2e@example.test",
        password_hash=hash_password("CampaignTest!2026"),
        role="coordinator", is_active=True,
        mfa_enabled_at=datetime.now(timezone.utc),
    )
    db_session.add(foreign_user)
    await db_session.commit()
    await db_session.refresh(foreign_user)
    foreign_token, _ = await create_user_session(db_session, foreign_user, tenant_b, aal=2)
    await db_session.commit()
    foreign_headers = {"Authorization": "Bearer " + foreign_token}
    foreign_read = await client.get(
        f"/api/v1/agents/retention/campaigns/intelligence/proposals/{proposal['id']}",
        headers=foreign_headers,
    )
    assert foreign_read.status_code == 404, foreign_read.text
    foreign_list = await client.get(
        "/api/v1/agents/retention/campaigns/intelligence/proposals", headers=foreign_headers
    )
    assert foreign_list.status_code == 200, foreign_list.text
    assert foreign_list.json()["count"] == 0
