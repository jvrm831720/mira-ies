"""Wave 6 integration: PostgreSQL trigram, RBAC, tenant scoping and partial providers."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select, text, update
from sqlalchemy.exc import SQLAlchemyError

from app.api.universal_search import parse_providers, search_universal
from app.models.auth import User
from app.models.object_view import ObjectView
from app.models.organization import ModuleEntitlement
from app.models.tenant import Tenant
from app.models.retention_campaign import RetentionCampaignProposal
from app.models.student import Student, UploadBatch
from app.models.work_activity import WorkActivity
from app.services.dispatch_core import bind_tenant
from app.services.federated_search_providers import PROVIDERS


def human(tenant_id: str, user_id: str, *, grants=None, role="coordinator"):
    return SimpleNamespace(
        tenant_id=tenant_id, user_id=user_id, session_id="session",
        aal=2, role=role, permissions=grants, custom_role_id=None,
    )


async def prepare_trigrams(db):
    # Separate ORM test DB is built via metadata.create_all rather than
    # running Alembic; the migrated database gate validates revision 072.
    await db.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
    await db.commit()


async def seed(db, tenant_id: str, tag: str, *, sensitive=False):
    # Match the server-authoritative GET /org/me profile/module contract.
    tenant = await db.get(Tenant, tenant_id)
    tenant.segment = "institution"
    existing_modules = set((await db.execute(select(ModuleEntitlement.module_key).where(
        ModuleEntitlement.tenant_id == tenant_id,
    ))).scalars().all())
    for module in ("workspace", "permanence", "billing"):
        if module not in existing_modules:
            db.add(ModuleEntitlement(
                tenant_id=tenant_id, module_key=module,
                status="enabled", source="test",
            ))
    await db.flush()
    user = User(
        tenant_id=tenant_id, email=f"search-{tag}-{uuid4()}@example.test",
        display_name="Operador " + tag, password_hash="test", role="coordinator",
        is_active=True,
    )
    db.add(user)
    await db.flush()
    user_id = user.id

    # Some earlier Wave 3 tests enable FORCE RLS in the shared disposable
    # database. Fixture writes must use the same explicit tenant/user context
    # that the real authenticated API provides; never bypass or disable RLS.
    await bind_tenant(db, tenant_id)
    await db.execute(
        text("SELECT set_config('app.user_id', :user_id, true)"),
        {"user_id": user_id},
    )

    batch = UploadBatch(
        tenant_id=tenant_id, filename="wave6.csv",
        original_filename="wave6.csv", status="processed",
    )
    db.add(batch)
    await db.flush()
    student = Student(
        tenant_id=tenant_id, batch_id=batch.id, matricula=f"M-{tag}",
        nome="Aline " + tag, curso="Graduação",
        communication_preferences={}, behavior_properties={},
    )
    task = WorkActivity(
        tenant_id=tenant_id, title="Revisar Aline " + tag,
        status="open", priority="normal", assignee_user_id=user_id,
    )
    view = ObjectView(
        tenant_id=tenant_id, owner_user_id=user_id, object_key="students",
        name="View Aline " + tag, scope="personal", is_sensitive=sensitive,
        config={}, config_version=1, revision=1,
    )
    proposal = RetentionCampaignProposal(
        tenant_id=tenant_id, title="Campanha Aline " + tag, status="draft",
        source_group_ids=[], source_catalog_version="v1",
        recommendation_engine="manual", source_evaluated_at=datetime.now(timezone.utc),
        objective="Acompanhar Aline", strategy="Ação humana",
        recommended_channels=["operacao_interna"], cadence_days=[0],
        message_brief="Ação interna", audience_snapshot=[], audience_hash="a" * 64,
        audience_total=0, outreach_eligible_count=0, blocked_count=0,
        internal_action_count=0,
    )
    db.add_all([student, task, view, proposal])
    await db.flush()
    ids = {
        "student": student.id, "task": task.id, "view": view.id,
        "campaign": proposal.id, "user": user_id,
    }
    await db.commit()

    await bind_tenant(db, tenant_id)
    obligation = str(uuid4())
    await db.execute(text("""
        INSERT INTO dispatch_obligations (
          id,tenant_id,external_ref,subject_type,subject_ref,status,balance,
          source,source_version,evidence_ref,verified_at)
        VALUES (:id,:tenant,:ref,'external',:subject,'open',100,
                'test_source',1,'evidence',:verified)
    """), {
        "id": obligation, "tenant": tenant_id,
        "ref": "CASE-ALINE-" + tag, "subject": "Aline " + tag,
        "verified": datetime.now(timezone.utc),
    })
    await db.commit()
    ids["case"] = obligation
    return ids


@pytest.mark.asyncio
async def test_all_providers_are_disambiguated_bounded_and_tenant_scoped(db_session, tenant_factory):
    await prepare_trigrams(db_session)
    a, _ = await tenant_factory(slug="search6-a")
    b, _ = await tenant_factory(slug="search6-b")
    a_id, b_id = a.id, b.id
    owner = await seed(db_session, a_id, "ALPHA")
    foreign = await seed(db_session, b_id, "BETA")
    # The direct endpoint call must emulate the request auth dependency RLS bind.
    await bind_tenant(db_session, a_id)
    response = await search_universal(
        q="Aline", limit=5, providers=None,
        auth=human(a_id, owner["user"]), db=db_session,
    )
    grouped = {row["category"] for row in response["results"]}
    assert grouped == {"students", "collections", "work", "views", "campaigns"}
    assert not response["partial"]
    assert response["count_scope"] == "bounded_matches_only"
    assert response["actions_executed"] is False
    assert response["returned"] <= 25
    ids = {row["id"] for row in response["results"]}
    assert set(owner.values()) - {owner["user"]} <= ids
    assert ids.isdisjoint(set(foreign.values()))
    assert all(row["href"].startswith("/") and "http" not in row["href"] for row in response["results"])
    assert all(row["kind"] == "navigate" for row in response["results"])
    assert "100" not in str(response["results"])
    assert "evidence" not in str(response["results"])


@pytest.mark.asyncio
async def test_custom_role_does_not_enumerate_forbidden_providers(db_session, tenant_factory):
    await prepare_trigrams(db_session)
    a, _ = await tenant_factory(slug="search6-rbac")
    tenant_id = a.id
    owner = await seed(db_session, tenant_id, "RBAC", sensitive=True)
    await bind_tenant(db_session, tenant_id)
    only_students = human(tenant_id, owner["user"],
                          grants=frozenset({"students.view"}), role="viewer")
    result = await search_universal(
        q="Aline", limit=5, providers=None, auth=only_students, db=db_session,
    )
    assert {row["category"] for row in result["results"]} == {"students"}
    assert owner["view"] not in {row["id"] for row in result["results"]}
    assert result["providers"]["collections"]["returned"] == 0
    assert result["providers"]["work"]["returned"] == 0
    assert result["providers"]["campaigns"]["returned"] == 0

    with pytest.raises(HTTPException) as denied:
        await search_universal(
            q="Aline", limit=5, providers=None,
            auth=SimpleNamespace(tenant_id=tenant_id, user_id=None, session_id=None, aal=1),
            db=db_session,
        )
    assert denied.value.status_code == 403


@pytest.mark.asyncio
async def test_partial_provider_error_is_isolated_and_opaque(db_session, tenant_factory, monkeypatch):
    await prepare_trigrams(db_session)
    tenant, _ = await tenant_factory(slug="search6-partial")
    tenant_id = tenant.id
    ids = await seed(db_session, tenant_id, "PARTIAL")
    # Direct function invocation skips get_current_tenant's RLS context binding.
    # Emulate the request dependency without weakening the provider policy.
    await bind_tenant(db_session, tenant_id)

    async def broken_provider(_context):
        raise SQLAlchemyError("internal SQL with private text")

    monkeypatch.setitem(PROVIDERS, "work", broken_provider)
    response = await search_universal(
        q="Aline", limit=3, providers="students,work,campaigns",
        auth=human(tenant_id, ids["user"]), db=db_session,
    )
    assert response["partial"] is True
    assert response["providers"]["work"] == {"status": "unavailable", "returned": 0}
    assert {row["category"] for row in response["results"]} == {"students", "campaigns"}
    assert "internal SQL" not in str(response)
    assert response["returned"] <= 6


@pytest.mark.asyncio
async def test_approximate_typo_and_limits(db_session, tenant_factory):
    await prepare_trigrams(db_session)
    tenant, _ = await tenant_factory(slug="search6-typo")
    tenant_id = tenant.id
    ids = await seed(db_session, tenant_id, "TYPO")
    await bind_tenant(db_session, tenant_id)
    student = Student(
        tenant_id=tenant_id, batch_id=(
            await db_session.execute(text(
                "SELECT id FROM upload_batches WHERE tenant_id=:t LIMIT 1"
            ), {"t": tenant_id})
        ).scalar_one(), matricula="M-MARIANA", nome="Mariana", curso="Administração",
        communication_preferences={}, behavior_properties={},
    )
    db_session.add(student)
    await db_session.commit()
    typo = await search_universal(
        q="Marina", limit=2, providers="students",
        auth=human(tenant_id, ids["user"]), db=db_session,
    )
    assert any(row["id"] == student.id for row in typo["results"])
    assert typo["limit_per_provider"] == 2
    assert all(row["category"] == "students" for row in typo["results"])
    for raw in ["students,unknown", "students,students", "", "students,work,campaigns,views,collections,unknown"]:
        with pytest.raises(HTTPException) as invalid:
            parse_providers(raw)
        assert invalid.value.status_code == 422


@pytest.mark.asyncio
async def test_disabled_billing_module_never_returns_financial_projections(db_session, tenant_factory):
    await prepare_trigrams(db_session)
    tenant, _ = await tenant_factory(slug="search6-module-denied")
    tenant_id = tenant.id
    owner = await seed(db_session, tenant_id, "ENTITLEMENT")
    await db_session.execute(update(ModuleEntitlement).where(
        ModuleEntitlement.tenant_id == tenant_id,
        ModuleEntitlement.module_key == "billing",
    ).values(status="disabled"))
    await db_session.commit()
    await bind_tenant(db_session, tenant_id)
    response = await search_universal(
        q="Aline", limit=5, providers=None,
        auth=human(tenant_id, owner["user"]), db=db_session,
    )
    assert "collections" not in {row["category"] for row in response["results"]}
    assert response["providers"]["collections"]["returned"] == 0
    assert owner["case"] not in {row["id"] for row in response["results"]}
    assert "students" in {row["category"] for row in response["results"]}



@pytest.mark.asyncio
async def test_api_key_cannot_search_public_or_private_data(client, tenant_factory):
    _, key = await tenant_factory(slug="search6-service-key")
    response = await client.get(
        "/api/v1/search/universal?q=Aline",
        headers={"X-API-Key": key},
    )
    assert response.status_code == 403
    # Request validators enforce hard bounds before any database search.
    oversized = await client.get(
        "/api/v1/search/universal?q=" + "x" * 81,
        headers={"X-API-Key": key},
    )
    assert oversized.status_code == 422
