"""Wave 6: negative RBAC, tenant boundaries, partial failure and bounded fuzzy search."""
from __future__ import annotations

import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.api import universal_search as search
from app.models.auth import User
from app.models.student import Student, UploadBatch
from app.models.work_activity import WorkActivity
from app.models.retention_campaign import RetentionCampaign
from app.models.object_view import ObjectView


def identity(tenant: str, user: str, grants: set[str]):
    return SimpleNamespace(
        tenant_id=tenant, user_id=user, session_id="verified-session",
        permissions=frozenset(grants), role="operator", custom_role_id="custom",
    )


async def set_rls(db, tenant: str, user: str):
    await db.execute(text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": tenant})
    await db.execute(text("SELECT set_config('app.user_id', :user, true)"), {"user": user})


async def create_data(db, tenant: str, suffix: str):
    u = User(
        tenant_id=tenant, display_name="Operator " + suffix,
        email=f"search6-{suffix}-{uuid4()}@example.test",
        password_hash="test", role="operator", is_active=True,
    )
    db.add(u)
    await db.flush()
    owner = u.id
    batch = UploadBatch(
        tenant_id=tenant, filename="wave6.csv", original_filename="wave6.csv",
        status="processed",
    )
    db.add(batch)
    await db.flush()
    student = Student(
        tenant_id=tenant, batch_id=batch.id, matricula="MAT" + suffix,
        nome="João " + suffix, curso="Ciências", communication_preferences={},
        behavior_properties={}, risk_score=99.0, email="secret@example.test",
        telefone="999999999",
    )
    db.add(student)
    db.add(WorkActivity(
        tenant_id=tenant, title="Revisar documento " + suffix, priority="high",
        status="open", assignee_user_id=owner, origin_type="manual",
    ))
    db.add(RetentionCampaign(
        tenant_id=tenant, slug="camp-" + suffix.lower(),
        name="Campanha revisão " + suffix, version=1, status="draft",
        archived=False, rules=[],
    ))
    db.add(ObjectView(
        tenant_id=tenant, owner_user_id=owner, object_key="students",
        name="Minha revisão " + suffix, scope="personal",
        is_sensitive=False, config_version=1, config={},
    ))
    await db.commit()
    return owner, student.id


def test_permissions_fail_closed_without_human_session_and_sensitive_grant():
    guest = SimpleNamespace(
        tenant_id=str(uuid4()), user_id=None, session_id=None,
        role=None, permissions=None, custom_role_id=None,
    )
    assert not any(search.permitted(guest, x) for x in search.PROVIDERS)
    own = identity(str(uuid4()), str(uuid4()), {"students.view"})
    assert search.permitted(own, "students")
    assert search.permitted(own, "views")
    assert not search.permitted(own, "collections")
    assert not search.permitted(own, "campaigns")
    assert not search.permitted(own, "work")  # access.operator is separately required
    privileged = identity(str(uuid4()), str(uuid4()), {
        "students.view", "access.operator", "campaigns.view", "audit.view",
    })
    assert all(search.permitted(privileged, x) for x in search.PROVIDERS)


def test_fuzzy_ranking_escaping_limits_and_no_financial_inference():
    assert search.escape_like("%_" + chr(92)) == chr(92) + "%" + chr(92) + "_" + chr(92) * 2
    assert search.normalized("JoÃO") == "joao"
    assert search.relevance("maria", "Maria") == (100, "exact")
    assert search.relevance("mari", "Maria")[1] == "prefix"
    score, match = search.relevance("joau", "Joao")
    assert score > 0 and match == "approximate"
    assert search.relevance("xx", "João")[0] == 0
    assert search.MAX_RESULTS == len(search.PROVIDERS) * search.MAX_PER_PROVIDER
    assert search.MAX_FUZZY_CANDIDATES <= 100


@pytest.mark.asyncio
async def test_tenant_isolation_all_categories_and_minimal_projection(
    tenant_factory, db_session, monkeypatch,
):
    ta, _ = await tenant_factory(slug="search6-tenant-a")
    tb, _ = await tenant_factory(slug="search6-tenant-b")
    a_id, b_id = ta.id, tb.id
    user_a, student_a = await create_data(db_session, a_id, "Alfa")
    await create_data(db_session, b_id, "Beta")
    await set_rls(db_session, a_id, user_a)

    # Collections have a separate verified dispatch schema. Isolate that
    # provider in this ORM-only test database and assert its failure behavior elsewhere.
    async def no_collection(*args):
        return []
    monkeypatch.setitem(search._SEARCHERS, "collections", no_collection)
    granted = identity(a_id, user_a, {
        "students.view", "students.sensitive.view", "access.operator",
        "campaigns.view", "audit.view",
    })
    for query, expected in (
        ("Alfa", {"students", "work", "views", "campaigns"}),
        ("Beta", set()),
    ):
        result = await search.federated_search(q=query, per_provider=5,
                                                auth=granted, db=db_session)
        returned = {r["provider"] for r in result["results"]}
        assert returned == expected
        assert result["partial"] is False
        assert result["count_scope"] == "bounded_matches"
        assert len(result["results"]) <= search.MAX_RESULTS
        assert all(r["action"] == "navigate" for r in result["results"])
        assert not any(token in json.dumps(result) for token in (
            "secret@example.test", "999999999", "risk_score", "shap_top_factors",
            "password_hash", "communication_preferences", "rules",
        ))
    j = await search.federated_search(q="João Alfa", per_provider=2,
                                      auth=granted, db=db_session)
    assert any(r["id"] == student_a and r["href"].startswith("/alunos/")
               for r in j["results"])
    # Narrow grants must not even attempt unpermitted source queries.
    narrow = identity(a_id, user_a, {"students.view"})
    filtered = await search.federated_search(q="Alfa", per_provider=5,
                                             auth=narrow, db=db_session)
    assert {r["provider"] for r in filtered["results"]} <= {"students", "views"}
    assert "collections" not in filtered["providers"]
    assert "campaigns" not in filtered["providers"]


@pytest.mark.asyncio
async def test_partial_provider_failure_survives_without_sql_disclosure(
    tenant_factory, db_session, monkeypatch,
):
    tenant, _ = await tenant_factory(slug="search6-partial")
    tenant_id = tenant.id
    owner, _ = await create_data(db_session, tenant_id, "Parcial")
    await set_rls(db_session, tenant_id, owner)
    async def broken(*args):
        raise RuntimeError("Sensitive SQL stacktrace / secrets / account numbers")
    monkeypatch.setitem(search._SEARCHERS, "collections", broken)
    result = await search.federated_search(
        q="Parcial", per_provider=2,
        auth=identity(tenant_id, owner, {"students.view", "audit.view"}),
        db=db_session,
    )
    assert result["partial"] is True
    assert result["unavailable"] == ["collections"]
    assert any(r["provider"] == "students" for r in result["results"])
    assert "Sensitive SQL" not in json.dumps(result)
    assert all(r["provider"] != "collections" for r in result["results"])


@pytest.mark.asyncio
async def test_financial_provider_projects_only_authorized_identifier_fields():
    row_id = str(uuid4())
    queries = []

    class Result:
        def __init__(self, data):
            self.data = data
        def mappings(self):
            return self
        def all(self):
            return self.data

    class Db:
        async def execute(self, statement, params=None):
            queries.append((str(statement), params))
            if "FROM dispatch_obligations" in str(statement):
                return Result([{
                    "id": row_id, "external_ref": "CASO-78",
                    "subject_ref": "MAT-78", "status": "open",
                    "source": "erp", "balance": "9999999",
                    "payload": "private",
                }])
            return Result([])

    tenant = str(uuid4())
    rows = await search._collections(Db(), identity(
        tenant, str(uuid4()), {"audit.view"},
    ), "CASO", 2)
    assert len(rows) == 1
    assert rows[0]["href"] == "/cobranca/casos/" + row_id
    assert rows[0]["provider"] == "collections"
    assert rows[0]["action"] == "navigate"
    assert rows[0]["match"] in {"prefix", "contains"}
    assert "9999999" not in json.dumps(rows)
    assert "private" not in json.dumps(rows)
    scoped = [(sql, params) for sql, params in queries if "dispatch_obligations" in sql]
    assert len(scoped) >= 1
    assert all("tenant_id = :tenant" in sql and params["tenant"] == tenant
               for sql, params in scoped)
    assert all(params["cap"] <= search.MAX_PER_PROVIDER * 4
               for _, params in scoped)


@pytest.mark.asyncio
async def test_service_key_denied_without_scanning_providers(db_session, monkeypatch):
    async def fail_if_called(*args):
        raise AssertionError("service key must never enumerate a provider")
    monkeypatch.setitem(search._SEARCHERS, "students", fail_if_called)
    with pytest.raises(HTTPException) as error:
        await search.federated_search(
            q="Ana", per_provider=5,
            auth=SimpleNamespace(tenant_id=str(uuid4()), user_id=None, session_id=None),
            db=db_session,
        )
    assert error.value.status_code == 403
