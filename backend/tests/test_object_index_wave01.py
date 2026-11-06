"""Wave 0.1: safe filters, paginated tenant query, saved-view policy and RLS."""
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import delete, select, text

from app.api.object_index import _student_sort, index_students
from app.api.object_views import CreateView, ViewSpec, require_view_access, validate_view
from app.models.auth import User
from app.models.object_view import ObjectView
from app.models.student import Student, UploadBatch
from app.services.object_index_filters import compile_filters


@pytest.mark.parametrize("raw", [
    '{"key":"risk_level","op":"eq","value":"baixo"}',
    '[{"key":"tenant_id","op":"eq","value":"other"}]',
    '[{"key":"risk_score","op":"contains","value":"20"}]',
    '[{"key":"nome","op":"contains","value":"%"},{"key":"foo","op":"eq","value":"x"}]',
    "not-json",
])
def test_rejects_unapproved_fields_and_malformed_filters(raw):
    with pytest.raises(HTTPException) as exc:
        compile_filters(raw)
    assert exc.value.status_code == 422


def test_accepts_allowlisted_filters_and_stable_sort():
    assert len(compile_filters('[{"key":"nome","op":"contains","value":"%"}]')) == 1
    assert len(compile_filters('[{"key":"risk_score","op":"between","value":[10,80]}]')) == 1
    assert len(_student_sort("risk_asc")) >= 2


def test_view_spec_strictly_rejects_extra_data_and_forbidden_fields():
    spec = ViewSpec(
        filters=[{"key": "risk_level", "op": "eq", "value": "critico"}],
        sort={"key": "risk_score", "desc": True},
        columns=["nome", "curso", "risk_score"],
    )
    validate_view("students", spec)
    with pytest.raises(ValidationError):
        CreateView(object_key="students", name="Query arbitrária", config={
            "version": 1, "filters": [], "sort": None, "columns": ["nome"],
            "raw_sql": "SELECT * FROM students",
        })
    with pytest.raises(HTTPException):
        validate_view("students", ViewSpec(filters=[{"key": "email", "op": "eq", "value": "x"}]))
    with pytest.raises(HTTPException):
        validate_view("students", ViewSpec(columns=["email"]))
    with pytest.raises(HTTPException):
        validate_view("students", ViewSpec(filters=[{"key": "risk_level", "op": "gt", "value": "baixo"}]))


def test_saved_views_require_human_identity_and_explicit_permission():
    with pytest.raises(HTTPException):
        require_view_access(SimpleNamespace(user_id=None, session_id=None), "students")
    with pytest.raises(HTTPException):
        require_view_access(SimpleNamespace(
            user_id=str(uuid4()), session_id=str(uuid4()), custom_role_id=str(uuid4()),
            role="viewer", permissions=frozenset({"access.viewer"}),
        ), "campaigns")
    require_view_access(SimpleNamespace(
        user_id=str(uuid4()), session_id=str(uuid4()), custom_role_id=None,
        role="viewer", permissions=frozenset({"students.view"}),
    ), "students")


@pytest.mark.asyncio
async def test_students_filtered_and_paginated_by_tenant(db_session, tenant_factory):
    tenant_a, _ = await tenant_factory(slug="object-index-a")
    tenant_b, _ = await tenant_factory(slug="object-index-b")
    for tenant, suffix in ((tenant_a, "a"), (tenant_b, "b")):
        await db_session.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tenant.id})
        batch = UploadBatch(tenant_id=tenant.id, filename="index.csv", original_filename="index.csv")
        db_session.add(batch)
        await db_session.flush()
        for score in (None, 15.0, 90.0):
            db_session.add(Student(
                tenant_id=tenant.id, batch_id=batch.id, matricula=f"{suffix}-{uuid4()}",
                nome=f"Aluno {suffix}", curso="Engenharia", risk_score=score,
                risk_level="critico" if score == 90 else "baixo" if score == 15 else None,
            ))
        await db_session.commit()
    auth = SimpleNamespace(tenant_id=tenant_a.id)
    await db_session.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tenant_a.id})

    kwargs = dict(q=None, course=None, risk_level=None, view="todos",
                  sort="risk_desc", filters=None, auth=auth, db=db_session)
    first = await index_students(limit=1, offset=0, **kwargs)
    assert first["total"] == 3 and first["has_more"]
    assert first["students"][0]["risk_score"] == 90
    second = await index_students(limit=2, offset=1, **kwargs)
    assert not second["has_more"] and second["students"][-1]["risk_score"] is None

    filtered = await index_students(
        limit=50, offset=0, **{**kwargs, "filters": '[{"key":"risk_score","op":"gt","value":50}]'},
    )
    assert filtered["total"] == 1
    assert filtered["students"][0]["risk_level"] == "critico"
    no_cross_tenant = await index_students(limit=50, offset=0, **{**kwargs, "q": "Aluno b"})
    assert no_cross_tenant["total"] == 0


@pytest.mark.asyncio
async def test_object_views_rls_enforces_tenant_and_user(db_session, tenant_factory):
    role_flags = (await db_session.execute(text(
        "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user"
    ))).scalar_one()
    assert role_flags is False, "RLS integration requires the non-superuser CI role."
    await db_session.execute(text("ALTER TABLE mira_object_views ENABLE ROW LEVEL SECURITY"))
    await db_session.execute(text("ALTER TABLE mira_object_views FORCE ROW LEVEL SECURITY"))
    await db_session.execute(text("DROP POLICY IF EXISTS mira_object_views_owner_policy ON mira_object_views"))
    await db_session.execute(text("""CREATE POLICY mira_object_views_owner_policy ON mira_object_views
        USING (
            tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
            AND owner_user_id = NULLIF(current_setting('app.user_id', true), '')::uuid
        )
        WITH CHECK (
            tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
            AND owner_user_id = NULLIF(current_setting('app.user_id', true), '')::uuid
        )"""))
    await db_session.commit()
    tenant_a, _ = await tenant_factory(slug="view-owner-a")
    tenant_b, _ = await tenant_factory(slug="view-owner-b")

    async def new_user(tenant, suffix):
        await db_session.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tenant.id})
        user = User(
            tenant_id=tenant.id, email=f"view-{suffix}-{uuid4()}@example.test",
            display_name="Test", password_hash="test-hash", role="viewer",
        )
        db_session.add(user)
        await db_session.commit()
        return user

    owner = await new_user(tenant_a, "owner")
    colleague = await new_user(tenant_a, "colleague")
    outsider = await new_user(tenant_b, "outsider")

    async def set_identity(tenant_id, user_id):
        await db_session.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tenant_id})
        await db_session.execute(text("SELECT set_config('app.user_id', :u, true)"), {"u": user_id})

    await set_identity(tenant_a.id, owner.id)
    view = ObjectView(
        tenant_id=tenant_a.id, owner_user_id=owner.id,
        object_key="students", name="Minha consulta",
        config_version=1,
        config={"version": 1, "filters": [], "columns": ["nome"], "sort": None, "page_size": 50},
    )
    db_session.add(view)
    await db_session.commit()
    assert view.id
    view_id = view.id
    cases = (
        (tenant_a.id, owner.id, 1),
        (tenant_a.id, colleague.id, 0),
        (tenant_b.id, outsider.id, 0),
    )
    for tenant_id, user_id, expected in cases:
        await set_identity(tenant_id, user_id)
        matches = (await db_session.execute(
            select(ObjectView).where(ObjectView.id == view_id)
        )).scalars().all()
        assert len(matches) == expected
        await db_session.rollback()

    # Explicit cleanup with the owner's row-security identity; no superuser bypass.
    await set_identity(cases[0][0], cases[0][1])
    await db_session.execute(delete(ObjectView).where(ObjectView.id == view_id))
    await db_session.commit()
