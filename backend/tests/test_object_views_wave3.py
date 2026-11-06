"""Wave 3: sharing, favorites, revision history, RLS and legacy views.

All tests use the app's non-superuser DB role and explicit PostgreSQL
transaction-local session context, never a superuser RLS bypass.
"""
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select, text

from app.api.object_views import (
    CreateView, DuplicateView, RestoreView, ShareView, UpdateView, ViewSpec,
    _view_config, can_share, create_view, duplicate_view, favorite_view,
    get_view, list_revisions, list_views, object_metadata, restore_view,
    share_view, unfavorite_view, update_view, validate_view,
)
from app.models.auth import User
from app.models.object_view import ObjectView, ObjectViewRevision


def context(tenant, user, *, role="coordinator", permissions=None):
    return SimpleNamespace(
        tenant_id=tenant, user_id=user, session_id=str(uuid4()),
        role=role, permissions=permissions, custom_role_id="custom" if permissions is not None else None,
    )


async def identity(db, tenant, user):
    await db.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tenant})
    await db.execute(text("SELECT set_config('app.user_id', :u, true)"), {"u": user})


def personal_view(name="Risco zero", columns=None):
    return CreateView(object_key="students", name=name,
                      config=ViewSpec(columns=columns or ["nome", "curso"], page_size=50))


def test_view_schema_keeps_revision_distinct_from_config_version():
    legacy = SimpleNamespace(
        object_key="students", config_version=1,
        config={"version": 1, "filters": [], "sort": None, "columns": ["nome"], "page_size": 50},
    )
    normal, state = _view_config(legacy)
    assert state == "upgraded"
    assert normal["version"] == 1
    assert normal["density"] == "comfortable"
    assert normal["sorts"] == []
    assert normal["property_labels"] == {}
    assert _view_config(SimpleNamespace(object_key="students", config_version=27, config={})) == (None, "unsupported")
    assert _view_config(SimpleNamespace(object_key="students", config_version=1,
                                        config={"version": 99})) == (None, "unsupported")


def test_invalid_metadata_and_sensitive_fields_fail_closed():
    with pytest.raises(HTTPException):
        validate_view("students", ViewSpec(columns=["fake_column"]))
    with pytest.raises(HTTPException):
        validate_view("students", ViewSpec(columns=["nome"], property_labels={"risk_score": "Parece público"}))
    with pytest.raises(ValidationError):
        ViewSpec(columns=["nome"], property_labels={"nome": "a"})
    with pytest.raises(HTTPException):
        validate_view("collections", ViewSpec(columns=["external_ref"], sorts=[{"key": "tenant_id", "desc": False}]))
    assert not can_share(context(str(uuid4()), str(uuid4()), permissions=frozenset({"students.view"})))
    assert can_share(context(str(uuid4()), str(uuid4()), role="coordinator"))


@pytest.mark.asyncio
async def test_workspace_sharing_favorite_revision_and_rls(db_session, tenant_factory):
    tenant_a, _ = await tenant_factory(slug="wave3-views-a")
    tenant_b, _ = await tenant_factory(slug="wave3-views-b")
    users = []
    for tenant, suffix in ((tenant_a, "owner"), (tenant_a, "peer"), (tenant_b, "outside")):
        user = User(
            tenant_id=tenant.id, email=f"views-{suffix}-{uuid4()}@example.test",
            display_name=suffix, password_hash="test", role="viewer",
        )
        await db_session.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tenant.id})
        db_session.add(user)
        await db_session.commit()
        users.append(user.id)
    owner, peer, outsider = users
    await identity(db_session, tenant_a.id, owner)
    owner_auth = context(tenant_a.id, owner)

    created = await create_view(personal_view(), auth=owner_auth, db=db_session)
    view_id = created["id"]
    assert created["scope"] == "personal"
    assert created["revision"] == 1 and created["version"] == 1
    assert created["can_share"]
    assert created["schema_status"] in ("current", "upgraded")
    assert len((await list_revisions(uuid4_from(view_id), auth=owner_auth, db=db_session))["revisions"]) == 1

    await identity(db_session, tenant_a.id, peer)
    peer_auth = context(tenant_a.id, peer, role="viewer")
    assert (await list_views("students", auth=peer_auth, db=db_session))["views"] == []
    raw = (await db_session.execute(select(ObjectView).where(ObjectView.id == view_id))).scalars().all()
    assert raw == [], "A view pessoal não deve vazar pelo SQL com RLS."

    await identity(db_session, tenant_a.id, owner)
    shared = await share_view(uuid4_from(view_id),
                              ShareView(scope="workspace", expected_revision=1),
                              auth=owner_auth, db=db_session)
    assert shared["scope"] == "workspace" and shared["revision"] == 2

    await identity(db_session, tenant_a.id, peer)
    peer_views = (await list_views("students", auth=peer_auth, db=db_session))["views"]
    assert [v["id"] for v in peer_views] == [view_id]
    assert not peer_views[0]["can_edit"] and not peer_views[0]["can_share"]
    await favorite_view(uuid4_from(view_id), auth=peer_auth, db=db_session)
    own = (await list_views("students", auth=peer_auth, db=db_session))["views"]
    assert own[0]["favorite"]
    await unfavorite_view(uuid4_from(view_id), auth=peer_auth, db=db_session)
    assert not (await list_views("students", auth=peer_auth, db=db_session))["views"][0]["favorite"]

    copy = await duplicate_view(uuid4_from(view_id), DuplicateView(name="Versão da equipe"),
                                auth=peer_auth, db=db_session)
    assert copy["scope"] == "personal" and copy["owner_user_id"] == peer
    assert copy["id"] != view_id and copy["revision"] == 1
    with pytest.raises(HTTPException) as exc:
        await update_view(uuid4_from(view_id),
                          UpdateView(name="Editar colega", expected_revision=2,
                                     config=ViewSpec(columns=["nome"])),
                          auth=peer_auth, db=db_session)
    assert exc.value.status_code == 404

    await identity(db_session, tenant_b.id, outsider)
    outsider_auth = context(tenant_b.id, outsider)
    assert (await list_views("students", auth=outsider_auth, db=db_session))["views"] == []
    with pytest.raises(HTTPException) as exc:
        await get_view(uuid4_from(view_id), auth=outsider_auth, db=db_session)
    assert exc.value.status_code == 404

    await identity(db_session, tenant_a.id, owner)
    changed = await update_view(uuid4_from(view_id), UpdateView(
        name="Nova visão", config=ViewSpec(
            columns=["nome", "curso"], property_labels={"curso": "Programa"},
        ), expected_revision=2), auth=owner_auth, db=db_session)
    assert changed["revision"] == 3
    assert changed["config"]["property_labels"]["curso"] == "Programa"
    with pytest.raises(HTTPException) as exc:
        await update_view(uuid4_from(view_id), UpdateView(
            name="Dados obsoletos", config=ViewSpec(columns=["nome"]), expected_revision=2),
            auth=owner_auth, db=db_session)
    assert exc.value.status_code == 409
    await db_session.rollback()
    await identity(db_session, tenant_a.id, owner)

    revisions = (await list_revisions(uuid4_from(view_id), auth=owner_auth, db=db_session))["revisions"]
    assert [item["revision"] for item in revisions] == [3, 2, 1]
    await identity(db_session, tenant_a.id, owner)
    restored = await restore_view(uuid4_from(view_id), RestoreView(
        revision=1, expected_revision=3), auth=owner_auth, db=db_session)
    assert restored["revision"] == 4 and restored["name"] == "Risco zero"
    assert restored["scope"] == "personal"
    assert restored["config"]["property_labels"] == {}
    history = (await db_session.execute(select(ObjectViewRevision).where(
        ObjectViewRevision.view_id == view_id))).scalars().all()
    assert len(history) == 4
    assert all(x.config_version == 1 for x in history)


@pytest.mark.asyncio
async def test_sensitive_shared_view_not_visible_to_basic_viewer(db_session, tenant_factory):
    tenant, _ = await tenant_factory(slug="wave3-sensitive")
    owner = User(tenant_id=tenant.id, email=f"owner-{uuid4()}@example.test",
                 display_name="Owner", password_hash="test", role="coordinator")
    peer = User(tenant_id=tenant.id, email=f"viewer-{uuid4()}@example.test",
                display_name="Viewer", password_hash="test", role="viewer")
    await db_session.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tenant.id})
    db_session.add_all([owner, peer])
    await db_session.commit()
    await identity(db_session, tenant.id, owner.id)
    author = context(tenant.id, owner.id)
    created = await create_view(personal_view(name="Risco sensível", columns=["nome", "risk_score"]),
                                auth=author, db=db_session)
    assert created["config"]["columns"] == ["nome", "risk_score"]
    await share_view(uuid4_from(created["id"]), ShareView(scope="workspace", expected_revision=1),
                     auth=author, db=db_session)

    await identity(db_session, tenant.id, peer.id)
    viewer = context(tenant.id, peer.id, role="viewer")
    assert (await list_views("students", auth=viewer, db=db_session))["views"] == []
    rows = (await db_session.execute(select(ObjectView).where(
        ObjectView.id == created["id"]))).scalars().all()
    assert rows == [], "RLS bloqueia configuração sensível de view compartilhada."
    metadata = await object_metadata("students", auth=viewer)
    assert "risk_score" not in [field["key"] for field in metadata["fields"]]
    with pytest.raises(HTTPException) as exc:
        await create_view(personal_view(name="Tentativa", columns=["nome", "risk_score"]),
                          auth=viewer, db=db_session)
    assert exc.value.status_code == 403


def uuid4_from(value):
    from uuid import UUID
    return UUID(value)
