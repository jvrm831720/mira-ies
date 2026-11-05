"""Dispatch platform gates and PostgreSQL isolation tests.

Requires the existing non-superuser PostgreSQL test environment.
No provider, webhook, or production endpoint is called by these tests.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import importlib.util
import hmac
import hashlib

import pytest
import pytest_asyncio
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text


@pytest_asyncio.fixture(scope="session", autouse=True)
async def dispatch_schema(_prepare_test_database):
    """Existing tests use metadata.create_all; materialize unmapped dispatch tables."""
    from app.db.session import engine

    migration_path = (Path(__file__).resolve().parents[1]
                      / "alembic" / "versions" / "055_dispatch_platform.py")
    spec = importlib.util.spec_from_file_location("dispatch_test_migration", migration_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    async with engine.begin() as conn:
        present = await conn.scalar(text("SELECT to_regclass('public.dispatch_campaigns')"))
        if not present:
            def _upgrade(connection):
                ctx = MigrationContext.configure(connection)
                with Operations.context(ctx):
                    module.upgrade()
            await conn.run_sync(_upgrade)
    yield


def test_policy_prohibits_collection_whatsapp():
    from app.services.dispatch_delivery import channel_allowed
    assert not channel_allowed("collections", "whatsapp")
    assert channel_allowed("collections", "email")
    assert channel_allowed("collections", "sms")


def test_contact_window_timezone_and_weekends():
    from app.services.dispatch_delivery import inside_contact_window
    weekday = datetime(2026, 11, 6, 14, 0, tzinfo=timezone.utc)
    assert inside_contact_window(weekday, "America/Sao_Paulo", 9, 18)
    night = datetime(2026, 11, 6, 2, 0, tzinfo=timezone.utc)
    assert not inside_contact_window(night, "America/Sao_Paulo", 9, 18)
    weekend = datetime(2026, 11, 7, 14, 0, tzinfo=timezone.utc)
    assert not inside_contact_window(weekend, "America/Sao_Paulo", 9, 18)


def test_reply_intent_never_proves_payment():
    from app.services.dispatch_core import classify_reply
    assert classify_reply("Já paguei. Tenho comprovante.") == ("claims_paid", "reconcile_payment")
    assert classify_reply("Não reconheço essa cobrança") == ("dispute", "human_review")
    assert classify_reply("STOP") == ("opt_out", "suppress_contact")
    assert classify_reply("Quero parcelar") == ("negotiate", "human_negotiation")


def test_provider_gate_is_closed_by_default(monkeypatch):
    from types import SimpleNamespace
    import app.services.dispatch_delivery as delivery

    monkeypatch.setattr(delivery, "get_settings", lambda: SimpleNamespace(
        dispatch_live_enabled=False, dispatch_live_tenants="tenant",
        dispatch_live_channels="email,sms",
    ))
    assert not delivery.live_enabled("tenant", "email")


def test_verified_webhook_requires_exact_signature(monkeypatch):
    from types import SimpleNamespace
    import app.api.dispatch_integrations as api

    secret = "a" * 48
    monkeypatch.setattr(api, "get_settings", lambda: SimpleNamespace(
        dispatch_webhook_secret=secret,
    ))
    raw = b'{"event":"test"}'
    signature = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    assert api.verify_gateway(raw, signature)
    assert not api.verify_gateway(raw + b" ", signature)
    assert not api.verify_gateway(raw, None)


@pytest.mark.asyncio
async def test_four_eyes_and_tenant_rls(db_session, tenant_factory):
    from app.services import dispatch_core as core

    tenant_a, _ = await tenant_factory("dispatch-a", "Dispatch A")
    tenant_b, _ = await tenant_factory("dispatch-b", "Dispatch B")
    campaign = await core.create_campaign(
        db_session, tenant_id=tenant_a.id, created_by="creator",
        name="Contato educativo", purpose="retention", channel="email",
        template_ref="Aviso institucional",
        template_body="Olá {nome}, entre em contato.",
    )
    assert campaign["status"] == "draft"
    with pytest.raises(ValueError):
        await core.transition_campaign(
            db_session, tenant_id=tenant_a.id,
            campaign_id=str(campaign["id"]), actor="creator",
            target="approved", authorization_ref="documento-1234",
        )
    # The row is hidden by forced RLS when the tenant context is changed.
    await core.bind_tenant(db_session, tenant_b.id)
    rows = await db_session.execute(text("SELECT id FROM dispatch_campaigns"))
    assert rows.all() == []


@pytest.mark.asyncio
async def test_outbox_deduplication_approval_and_simulated_send(
    db_session, tenant, monkeypatch,
):
    import app.services.dispatch_delivery as delivery
    from app.services import dispatch_core as core
    from app.dispatch_worker import claim_batch, process_item
    from app.models.student import Student, UploadBatch

    tenant_row, _ = tenant
    batch = UploadBatch(
        tenant_id=tenant_row.id, filename="dispatch-test.csv",
        original_filename="dispatch-test.csv", status="processed",
    )
    db_session.add(batch)
    await db_session.flush()
    student = Student(
        tenant_id=tenant_row.id, batch_id=batch.id,
        matricula="DISP001", nome="Ana", email="ana@example.test",
        communication_preferences={"channels": {"email": True}},
    )
    db_session.add(student)
    await db_session.commit()
    await db_session.refresh(student)

    campaign = await core.create_campaign(
        db_session, tenant_id=tenant_row.id, created_by="creator",
        name="Aviso de permanência", purpose="retention", channel="email",
        template_ref="Comunicado institucional",
        template_body="Olá {nome}, fale com nossa equipe.",
    )
    campaign_id = str(campaign["id"])
    target = {
        "subject_type": "student", "subject_ref": student.id,
        "consent_ref": "contact-reference-001",
    }
    first = await core.enqueue_recipients(
        db_session, tenant_id=tenant_row.id, campaign_id=campaign_id,
        targets=[target], actor="creator",
    )
    second = await core.enqueue_recipients(
        db_session, tenant_id=tenant_row.id, campaign_id=campaign_id,
        targets=[target], actor="creator",
    )
    assert first["created"] == 1
    assert second["duplicates"] == 1

    with pytest.raises(ValueError, match="outro usuário"):
        await core.transition_campaign(
            db_session, tenant_id=tenant_row.id, campaign_id=campaign_id,
            actor="creator", target="approved",
            authorization_ref="institutional-authorization",
        )
    approved = await core.transition_campaign(
        db_session, tenant_id=tenant_row.id, campaign_id=campaign_id,
        actor="second-user", target="approved",
        authorization_ref="institutional-authorization",
    )
    assert approved["status"] == "approved"
    await core.transition_campaign(
        db_session, tenant_id=tenant_row.id, campaign_id=campaign_id,
        actor="second-user", target="running",
    )

    monkeypatch.setattr(delivery, "inside_contact_window", lambda *args: True)
    monkeypatch.setattr(delivery, "live_enabled", lambda *_args: False)
    claimed = await claim_batch(db_session, tenant_row.id, "worker-test", limit=10)
    assert len(claimed) == 1
    status = await process_item(
        tenant_id=tenant_row.id, item_id=str(claimed[0]["id"]),
        token=str(claimed[0]["lease_token"]), owner="worker-test",
    )
    assert status == "simulated"
    await core.bind_tenant(db_session, tenant_row.id)
    state = (await db_session.execute(text("""
        SELECT status,provider FROM dispatch_items
        WHERE tenant_id=:tenant AND campaign_id=:campaign
    """), {"tenant": tenant_row.id, "campaign": campaign_id})).one()
    assert state.status == "simulated"
    assert state.provider == "simulation"


@pytest.mark.asyncio
async def test_stale_sending_becomes_unknown_never_requeued(db_session, tenant):
    from app.services import dispatch_core as core
    from app.dispatch_worker import claim_batch, recover_expired_leases
    from app.models.student import Student, UploadBatch

    org, _ = tenant
    batch = UploadBatch(
        tenant_id=org.id, filename="unknown.csv",
        original_filename="unknown.csv", status="processed",
    )
    db_session.add(batch)
    await db_session.flush()
    student = Student(
        tenant_id=org.id, batch_id=batch.id,
        matricula="DISP-UNKNOWN", nome="Pessoa", email="pessoa@example.test",
    )
    db_session.add(student)
    await db_session.commit()
    await db_session.refresh(student)
    campaign = await core.create_campaign(
        db_session, tenant_id=org.id, created_by="creator",
        name="Comunicação teste", purpose="retention", channel="email",
        template_ref="Aviso", template_body="Mensagem de teste",
    )
    campaign_id = str(campaign["id"])
    await core.enqueue_recipients(
        db_session, tenant_id=org.id, campaign_id=campaign_id,
        targets=[{"subject_type":"student","subject_ref":student.id,
                  "consent_ref":"reference-unknown"}], actor="creator",
    )
    await core.transition_campaign(
        db_session, tenant_id=org.id, campaign_id=campaign_id,
        actor="approver", target="approved", authorization_ref="reference-approved",
    )
    await core.transition_campaign(
        db_session, tenant_id=org.id, campaign_id=campaign_id,
        actor="approver", target="running",
    )
    claimed = await claim_batch(db_session, org.id, "worker", 1)
    assert len(claimed) == 1
    await core.bind_tenant(db_session, org.id)
    await db_session.execute(text("""
        UPDATE dispatch_items SET status='sending',
          lease_until=now() - interval '3 minutes'
        WHERE tenant_id=:tenant AND id=:id
    """), {"tenant": org.id, "id": claimed[0]["id"]})
    await db_session.commit()
    recovered = await recover_expired_leases(db_session, org.id)
    assert recovered == {"requeued": 0, "unknown": 1}
    assert await claim_batch(db_session, org.id, "another", 1) == []
