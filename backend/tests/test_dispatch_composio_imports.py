"""Composio-to-dispatch execution tests; never connect to remote credentials."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import text

from app.services import dispatch_composio_imports as ing


def test_tool_session_executes_only_named_read_account(monkeypatch):
    seen: dict = {}

    class Session:
        def execute(self, slug, *, arguments, account):
            seen["execution"] = (slug, arguments, account)
            return SimpleNamespace(
                result_type="completed",
                data={"items": [{"id": "contact-1", "customer_id": "external-1", "email": "a@example.test"}]},
            )

    class Sessions:
        def create(self, **kwargs):
            seen["session"] = kwargs
            return Session()

    monkeypatch.setattr(ing, "get_composio_client", lambda: SimpleNamespace(sessions=Sessions()))
    result = ing._execute_single_read(
        user_id="tenant-identity-opaque", account_id="ca-001", toolkit="gmail",
        tool_slug="GMAIL_LIST_MESSAGES", arguments={"max_results": 1},
    )
    assert result["items"][0]["id"] == "contact-1"
    assert seen["session"]["user_id"] == "tenant-identity-opaque"
    assert seen["session"]["toolkits"] == ["gmail"]
    assert seen["session"]["tools"] == {"gmail": {"enable": ["GMAIL_LIST_MESSAGES"]}}
    assert seen["session"]["connected_accounts"] == {"gmail": ["ca-001"]}
    assert seen["session"]["manage_connections"] == {"enable": False}
    assert seen["session"]["sandbox"] == {"enable": False}
    assert seen["execution"] == (
        "GMAIL_LIST_MESSAGES", {"max_results": 1}, "ca-001",
    )


def test_composio_failed_tool_result_never_imported(monkeypatch):
    class Session:
        def execute(self, *args, **kwargs):
            return SimpleNamespace(
                result_type="failed", data={"items": [{"id": "unsafe"}]},
            )

    monkeypatch.setattr(ing, "get_composio_client", lambda: SimpleNamespace(
        sessions=SimpleNamespace(create=lambda **kwargs: Session()),
    ))
    with pytest.raises(ing.ComposioIngestDenied):
        ing._execute_single_read(
            user_id="tenant", account_id="ca-a", toolkit="gmail",
            tool_slug="GMAIL_LIST_MESSAGES", arguments={},
        )


def test_composio_mapping_only_keeps_explicit_canonical_fields():
    raw = {"data": {"contacts": [
        {"id": "CRM-1", "account": {"id": "subject-a"}, "email": "a@example.test",
         "ssn": "must-not-import", "secret": {"token": "sensitive"}},
        {"id": "CRM-2", "account": {"id": "subject-b"}, "email": "b@example.test"},
    ]}}
    records = ing.normalize_rows(
        raw, rows_path="data.contacts", record_id_field="id",
        subject_ref_field="account.id", subject_type="external",
        record_type="contact", field_map={"email": "email"},
    )
    assert len(records) == 2
    assert records[0] == {
        "source_record_id": "CRM-1", "subject_ref": "subject-a",
        "subject_type": "external", "record_type": "contact",
        "values": {"email": "a@example.test"},
    }
    assert "ssn" not in str(records)
    assert "sensitive" not in str(records)


@pytest.mark.parametrize("rows, message", [
    ([{"id": "duplicate"}, {"id": "duplicate"}], "duplicados"),
    ([{"id": {"nested": "not-valid"}}], "escalares"),
])
def test_composio_rejects_ambiguous_or_duplicate_records(rows, message):
    with pytest.raises(ing.ComposioIngestDenied, match=message):
        ing.normalize_rows(
            {"items": rows}, rows_path="items", record_id_field="id",
            subject_ref_field="id", subject_type="external", record_type="generic",
            field_map={},
        )


def test_composio_read_ingestion_is_independently_feature_gated(monkeypatch):
    cfg = SimpleNamespace(
        composio_enabled=True, composio_api_key="not-real",
        composio_identity_secret="x" * 40,
        composio_tool_execution_enabled=False,
        dispatch_composio_ingestion_enabled=True,
        dispatch_composio_ingestion_read_tools="GMAIL_LIST_MESSAGES",
    )
    monkeypatch.setattr(ing, "get_settings", lambda: cfg)
    ing._require_enabled()
    assert ing._tool_allowed("GMAIL_LIST_MESSAGES")
    assert not ing._tool_allowed("GMAIL_SEND_EMAIL")
    assert not ing._tool_allowed("GMAIL_GET_AND_DELETE_MESSAGE")
    cfg.dispatch_composio_ingestion_enabled = False
    with pytest.raises(ing.ComposioIngestDenied):
        ing._require_enabled()


@pytest.mark.asyncio
async def test_real_import_path_is_tenant_isolated_encrypted_and_idempotent(
    db_session, tenant_factory, monkeypatch,
):
    """Fake Composio I/O only; Postgres and RLS are real."""
    from app.models.auth import User
    from app.models.composio_connection import (
        TenantComposioAccount, TenantComposioSession, TenantComposioToolkitPolicy,
    )
    from app.services.dispatch_core import bind_tenant

    org_a, _ = await tenant_factory("composio-import-a", "Import A")
    org_b, _ = await tenant_factory("composio-import-b", "Import B")
    user = User(
        tenant_id=org_a.id, display_name="Operator", email="operator-a@example.test",
        password_hash="not-real", role="admin",
    )
    db_session.add(user)
    await db_session.flush()
    db_session.add_all([
        TenantComposioSession(
            tenant_id=org_a.id, composio_user_id="tenant-composio-a", status="active",
        ),
        TenantComposioAccount(
            tenant_id=org_a.id, toolkit_slug="gmail",
            connected_account_id="ca-test-a", status="active",
        ),
        TenantComposioToolkitPolicy(
            tenant_id=org_a.id, toolkit_slug="gmail", is_enabled=True,
            tool_slugs=["GMAIL_LIST_MESSAGES"],
        ),
    ])
    await db_session.commit()

    cfg = SimpleNamespace(
        composio_enabled=True, composio_api_key="dummy-not-live",
        composio_identity_secret="x" * 40,
        composio_allowed_toolkits="gmail", composio_tool_execution_enabled=False,
        dispatch_composio_ingestion_enabled=True,
        dispatch_composio_ingestion_read_tools="GMAIL_LIST_MESSAGES",
        dispatch_composio_data_key=Fernet.generate_key().decode(),
    )
    import app.services.dispatch_sources as sources
    monkeypatch.setattr(ing, "get_settings", lambda: cfg)
    monkeypatch.setattr(sources, "get_settings", lambda: cfg)
    monkeypatch.setattr(ing, "_tool_schema", lambda toolkit, tool: {
        "type": "object", "properties": {}, "required": [],
        "additionalProperties": False,
    })
    monkeypatch.setattr(ing, "_verify_remote_account", lambda **kwargs: {
        "connected_account_id": "ca-test-a", "user_id": "tenant-composio-a",
        "toolkit_slug": "gmail", "status": "active",
    })
    import_counter = {"calls": 0}

    def fake_read(**kwargs):
        import_counter["calls"] += 1
        assert kwargs["user_id"] == "tenant-composio-a"
        assert kwargs["account_id"] == "ca-test-a"
        return {"items": [
            {"id": "remote-1", "subject": "external-1", "email": "someone@example.test"},
        ]}

    monkeypatch.setattr(ing, "_execute_single_read", fake_read)
    kwargs = dict(
        tenant_id=org_a.id, actor_id=user.id, account_id="ca-test-a",
        tool_slug="GMAIL_LIST_MESSAGES", arguments={}, rows_path="items",
        record_id_field="id", subject_ref_field="subject",
        subject_type="external", record_type="contact",
        field_map={"email": "email"}, idempotency_key="test-import-00000001",
    )
    created = await ing.import_read_tool(db_session, **kwargs)
    assert created["status"] == "succeeded"
    assert created["total"] == 1
    assert created["created"] == 1
    assert created["deduplicated"] is False
    again = await ing.import_read_tool(db_session, **kwargs)
    assert again["deduplicated"]
    assert import_counter["calls"] == 1

    await bind_tenant(db_session, org_a.id)
    rows = (await db_session.execute(text("""
        SELECT payload_ciphertext,payload_hash,source_record_id
        FROM dispatch_source_observations WHERE tenant_id=:tenant
    """), {"tenant": org_a.id})).mappings().all()
    assert len(rows) == 1
    assert rows[0]["source_record_id"] == "remote-1"
    assert "someone@example.test" not in rows[0]["payload_ciphertext"]
    assert ing._decrypt_values(rows[0]["payload_ciphertext"]) == {
        "email": "someone@example.test",
    }
    await bind_tenant(db_session, org_b.id)
    assert (await db_session.execute(text(
        "SELECT count(*) FROM dispatch_source_observations"
    ))).scalar_one() == 0
    assert (await db_session.execute(text(
        "SELECT count(*) FROM dispatch_source_import_runs"
    ))).scalar_one() == 0


@pytest.mark.asyncio
async def test_staging_imported_records_never_grants_contact_authorization(
    db_session, tenant_factory, monkeypatch,
):
    """With no MIRA authorization and contact, a Composio record cannot queue."""
    from app.models.composio_connection import (
        TenantComposioAccount, TenantComposioSession, TenantComposioToolkitPolicy,
    )
    from app.services import dispatch_sources as sources, dispatch_core
    from app.services.dispatch_core import bind_tenant
    from uuid import uuid4

    org, _ = await tenant_factory("composio-stage-a", "Stage A")
    db_session.add_all([
        TenantComposioSession(
            tenant_id=org.id, composio_user_id="stage-tenant-a", status="active",
        ),
        TenantComposioAccount(
            tenant_id=org.id, toolkit_slug="gmail",
            connected_account_id="ca-stage-a", status="active",
        ),
        TenantComposioToolkitPolicy(
            tenant_id=org.id, toolkit_slug="gmail", is_enabled=True,
            tool_slugs=["GMAIL_LIST_MESSAGES"],
        ),
    ])
    await db_session.commit()
    cfg = SimpleNamespace(
        composio_enabled=True, composio_api_key="dummy",
        composio_identity_secret="x" * 40,
        composio_allowed_toolkits="gmail", composio_tool_execution_enabled=False,
        dispatch_composio_ingestion_enabled=True,
        dispatch_composio_ingestion_read_tools="GMAIL_LIST_MESSAGES",
        dispatch_composio_data_key=Fernet.generate_key().decode(),
        dispatch_trusted_authorization_sources="test_registry",
    )
    monkeypatch.setattr(ing, "get_settings", lambda: cfg)
    monkeypatch.setattr(sources, "get_settings", lambda: cfg)
    campaign = await dispatch_core.create_campaign(
        db_session, tenant_id=org.id, created_by="human-operator",
        name="Atendimento assistido", purpose="service",
        channel="email", template_ref="Mensagem institucional",
        template_body="Olá {nome}, como podemos ajudar?",
        source_kind="composio", source_ref="ca-stage-a",
        source_tool_slug="GMAIL_LIST_MESSAGES",
    )
    await bind_tenant(db_session, org.id)
    await db_session.execute(text("""
        INSERT INTO dispatch_source_observations (
          id,tenant_id,connected_account_id,toolkit_slug,tool_slug,
          source_record_id,subject_type,subject_ref,record_type,
          payload_ciphertext,payload_hash
        ) VALUES (
          :id,:tenant,'ca-stage-a','gmail','GMAIL_LIST_MESSAGES',
          'record-1','external','external-1','contact',:cipher,:hash
        )
    """), {
        "id": str(uuid4()), "tenant": org.id,
        "cipher": ing._encrypt_values({"email": "someone@example.test"}),
        "hash": "a" * 64,
    })
    await db_session.commit()
    outcome = await ing.stage_authorized_observations(
        db_session, tenant_id=org.id, actor_id="human-operator",
        campaign_id=str(campaign["id"]), source_record_ids=[],
    )
    assert outcome == {"created": 0, "duplicates": 0, "filtered": 1}
    await bind_tenant(db_session, org.id)
    assert (await db_session.execute(text("""
        SELECT count(*) FROM dispatch_items WHERE tenant_id=:tenant
    """), {"tenant": org.id})).scalar_one() == 0
