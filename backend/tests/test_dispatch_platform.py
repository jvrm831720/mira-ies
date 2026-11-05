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


from datetime import timedelta
from uuid import uuid4
from app.core.config import get_settings


@pytest.fixture(autouse=True)
def dispatch_trusted_test_source(monkeypatch):
    # Test-only authorization registry; no production source is implicitly trusted.
    monkeypatch.setattr(get_settings(), "dispatch_trusted_authorization_sources", "test_registry")
    from cryptography.fernet import Fernet
    monkeypatch.setattr(get_settings(), "dispatch_source_encryption_key",
                        Fernet.generate_key().decode())


async def source_test_secret(db,tenant_id,source,scope):
    from app.services import dispatch_ingress_security as gate
    registered=await gate.configure(
        db,tenant_id=tenant_id,actor="source-manager",
        source=source,scope=scope,
    )
    await gate.activate(
        db,tenant_id=tenant_id,actor="source-approver",
        source=source,scope=scope,evidence="source-approval-001",
    )
    return registered["secret_once"]


async def signed_post(client,key,source,secret,path,payload):
    import json
    import secrets
    import time
    from app.services.dispatch_ingress_security import signature
    raw=json.dumps(payload,separators=(",",":"),ensure_ascii=False).encode()
    timestamp=str(int(time.time()))
    nonce=secrets.token_urlsafe(24)
    headers={
        "X-API-Key":key,"Content-Type":"application/json",
        "X-Mira-Source":source,
        "X-Mira-Timestamp":timestamp,
        "X-Mira-Nonce":nonce,
        "X-Mira-Signature":signature(secret,timestamp,nonce,"POST",path,raw),
    }
    return await client.post(path,headers=headers,content=raw)


async def seed_authorizations(db, tenant_id: str, references: list[str],
                              evidence: str, purpose: str = "retention") -> None:
    from app.services import dispatch_core as core
    await core.bind_tenant(db, tenant_id)
    now = datetime.now(timezone.utc)
    for ref in references:
        await db.execute(text("""
            INSERT INTO dispatch_authorizations (
                id,tenant_id,subject_type,subject_ref,channel,purpose,
                evidence_ref,source,status,verified_at,expires_at
            ) VALUES (:id,:tenant,'student',:ref,'email',:purpose,
                      :evidence,'test_registry','granted',:verified,:expires)
        """), {
            "id":str(uuid4()),"tenant":tenant_id,"ref":ref,"purpose":purpose,
            "evidence":evidence,"verified":now,
            "expires":now+timedelta(days=7),
        })
    await db.commit()


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
        dispatch_live_enabled=False, dispatch_worker_enabled=False,
        dispatch_dry_run_default=True, dispatch_live_tenants="tenant",
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

    privileged = (await db_session.execute(text("""
        SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname=current_user
    """))).scalar_one()
    if privileged:
        pytest.skip("RLS precisa de papel PostgreSQL sem SUPERUSER/BYPASSRLS.")
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
        communication_preferences={"channels": {"email": True},
                                   "topics": {"retention": True}},
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
    await seed_authorizations(
        db_session, tenant_row.id, [student.id], "contact-reference-001",
    )
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
    await seed_authorizations(db_session, org.id, [student.id], "reference-unknown")
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


@pytest.mark.asyncio
async def test_connector_reconciliation_blocks_paid_debt_and_deduplicates(
    client, db_session, tenant,
):
    from app.services import dispatch_core as core

    org, key = tenant
    secret = await source_test_secret(db_session,org.id,"test_erp","financial")
    ref = "invoice-001"
    body = {
        "external_ref": ref, "subject_type": "external",
        "subject_ref": "opaque-customer-a", "status": "open",
        "balance": "150.00", "source": "test_erp",
        "evidence_ref": "erp:verified:invoice-001",
        "source_version": 1,
        "observed_at": datetime.now(timezone.utc).isoformat(),
    }
    created = await signed_post(
        client,key,"test_erp",secret,
        "/api/v1/dispatch/integrations/obligations",body,
    )
    assert created.status_code == 200, created.text
    await core.bind_tenant(db_session, org.id)
    assert (await db_session.execute(text("""
        SELECT status FROM dispatch_obligations WHERE tenant_id=:tenant AND external_ref=:ref
    """), {"tenant": org.id, "ref": ref})).scalar_one() == "open"

    payment = {
        "obligation_ref": ref, "source": "test_erp",
        "source_event_id": "payment-test-0001", "amount_paid": "150.00",
        "evidence_ref": "erp:verified:payment-0001",
        "new_status": "paid", "balance": "0.00",
        "source_version": 2,
        "observed_at": (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat(),
    }
    result = await signed_post(
        client,key,"test_erp",secret,
        "/api/v1/dispatch/integrations/payments",payment,
    )
    assert result.status_code == 200, result.text
    assert result.json() == {"accepted": True, "replayed": False, "status": "paid"}
    replay = await signed_post(
        client,key,"test_erp",secret,
        "/api/v1/dispatch/integrations/payments",payment,
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["replayed"] is True

    changed = await signed_post(
        client,key,"test_erp",secret,
        "/api/v1/dispatch/integrations/payments",
        {**payment,"amount_paid":"250.00"},
    )
    assert changed.status_code == 409

    await core.bind_tenant(db_session, org.id)
    paid = (await db_session.execute(text("""
        SELECT count(*) FROM dispatch_payment_events WHERE tenant_id=:tenant
    """), {"tenant": org.id})).scalar_one()
    assert paid == 1
    obligation = (await db_session.execute(text("""
        SELECT status,balance FROM dispatch_obligations
        WHERE tenant_id=:tenant AND external_ref=:ref
    """), {"tenant": org.id, "ref": ref})).one()
    assert obligation.status == "paid" and obligation.balance == 0

    stale = await signed_post(
        client,key,"test_erp",secret,
        "/api/v1/dispatch/integrations/obligations",
        {**body,"source_version":1,"status":"open",
         "observed_at": datetime.now(timezone.utc).isoformat()},
    )
    assert stale.status_code in {200,409}
    assert stale.status_code == 409  # version 1 cannot roll back version 2
    later = await signed_post(
        client,key,"test_erp",secret,
        "/api/v1/dispatch/integrations/obligations",
        {**body,"source_version":3,
         "observed_at":datetime.now(timezone.utc).isoformat()},
    )
    assert later.status_code == 409  # a settled obligation never reopens



@pytest.mark.asyncio
async def test_connector_contacts_are_encrypted_and_api_keys_cannot_approve(
    client, db_session, tenant, monkeypatch,
):
    from types import SimpleNamespace
    from cryptography.fernet import Fernet
    import app.services.dispatch_delivery as delivery

    org, key = tenant
    secret = await source_test_secret(db_session,org.id,"test_contacts","contacts")
    monkeypatch.setattr(delivery, "get_settings", lambda: SimpleNamespace(
        dispatch_contact_encryption_key=Fernet.generate_key().decode(),
    ))
    headers = {"X-API-Key": key}
    created = await signed_post(
        client,key,"test_contacts",secret,
        "/api/v1/dispatch/integrations/contacts",{
            "source":"test_contacts",
            "subject_ref":"opaque-external-ref",
            "channel":"email","recipient":"person@example.test",
            "consent_ref":"verified-basis-001","opt_out":False,
        },
    )
    assert created.status_code == 200, created.text
    from app.services.dispatch_core import bind_tenant
    await bind_tenant(db_session, org.id)
    encrypted = (await db_session.execute(text("""
        SELECT recipient_ciphertext FROM dispatch_external_contacts
        WHERE tenant_id=:tenant
    """), {"tenant": org.id})).scalar_one()
    assert "person@example.test" not in encrypted
    rejected = await client.post(
        "/api/v1/dispatch/campaigns",
        headers=headers, json={
            "name": "Unauthorized Campaign",
            "purpose": "retention", "channel": "email",
            "template_ref": "Test", "template_body": "Hello",
        },
    )
    assert rejected.status_code == 403


@pytest.mark.asyncio
async def test_signed_gateway_never_counts_reply_as_payment(
    client, db_session, tenant, monkeypatch,
):
    from types import SimpleNamespace
    import json
    import app.api.dispatch_integrations as integrations
    from app.services import dispatch_core as core
    from app.models.student import Student, UploadBatch

    org, _ = tenant
    batch = UploadBatch(
        tenant_id=org.id, filename="reply.csv", original_filename="reply.csv",
        status="processed",
    )
    db_session.add(batch)
    await db_session.flush()
    student = Student(tenant_id=org.id, batch_id=batch.id,
                      matricula="REPLY-001", nome="Bruna", email="bruna@example.test")
    db_session.add(student)
    await db_session.commit()
    await db_session.refresh(student)
    campaign = await core.create_campaign(
        db_session, tenant_id=org.id, created_by="creator",
        name="Reply test", purpose="retention", channel="email",
        template_ref="Aviso", template_body="Mensagem",
    )
    await seed_authorizations(db_session, org.id, [student.id], "contact-policy-0001")
    await core.enqueue_recipients(
        db_session, tenant_id=org.id, campaign_id=str(campaign["id"]),
        targets=[{
            "subject_type": "student", "subject_ref": student.id,
            "consent_ref": "contact-policy-0001",
        }], actor="creator",
    )
    await core.bind_tenant(db_session, org.id)
    await db_session.execute(text("""
        UPDATE dispatch_items
        SET status='sent',provider='resend',provider_message_id='provider-msg-001',
            sent_at=now()
        WHERE tenant_id=:tenant AND campaign_id=:id
    """), {"tenant": org.id, "id": campaign["id"]})
    await db_session.commit()

    secret = "signed-gateway-secret-0123456789-abcdef"
    monkeypatch.setattr(integrations, "get_settings", lambda: SimpleNamespace(
        dispatch_webhook_secret=secret,
    ))
    event = {
        "tenant_id": org.id, "provider_message_id": "provider-msg-001",
        "external_event_id": "gateway-event-0001", "kind": "reply",
        "message": "Já paguei, preciso que vocês verifiquem.",
    }
    raw = json.dumps(event, separators=(",", ":")).encode()
    signature = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    response = await client.post(
        "/api/v1/dispatch/webhooks/resend", content=raw,
        headers={"X-Mira-Dispatch-Signature": signature, "Content-Type": "application/json"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["intent"] == "claims_paid"
    replay = await client.post(
        "/api/v1/dispatch/webhooks/resend", content=raw,
        headers={"X-Mira-Dispatch-Signature": signature, "Content-Type": "application/json"},
    )
    assert replay.json()["replayed"] is True
    await core.bind_tenant(db_session, org.id)
    assert (await db_session.execute(text("""
        SELECT count(*) FROM dispatch_payment_events WHERE tenant_id=:tenant
    """), {"tenant": org.id})).scalar_one() == 0


@pytest.mark.asyncio
async def test_concurrent_workers_claim_disjoint_items(db_session, tenant):
    """FOR UPDATE SKIP LOCKED must not hand one recipient to two workers."""
    import asyncio
    from app.db.session import AsyncSessionLocal
    from app.models.student import Student, UploadBatch
    from app.services import dispatch_core as core
    from app.dispatch_worker import claim_batch

    org, _ = tenant
    batch = UploadBatch(
        tenant_id=org.id, filename="load.csv",
        original_filename="load.csv", status="processed",
    )
    db_session.add(batch)
    await db_session.flush()
    students = [
        Student(
            tenant_id=org.id, batch_id=batch.id,
            matricula=f"LOAD-{index:04d}", nome=f"Pessoa {index}",
            email=f"person{index}@example.test",
            communication_preferences={"channels": {"email": True},
                                   "topics": {"retention": True}},
        ) for index in range(30)
    ]
    db_session.add_all(students)
    await db_session.commit()

    campaign = await core.create_campaign(
        db_session, tenant_id=org.id, created_by="creator",
        name="Teste de concorrência", purpose="retention", channel="email",
        template_ref="Template de simulação", template_body="Olá {nome}.",
    )
    campaign_id = str(campaign["id"])
    await seed_authorizations(
        db_session, org.id, [student.id for student in students],
        "test-authorized-record",
    )
    staged = await core.enqueue_recipients(
        db_session, tenant_id=org.id, campaign_id=campaign_id,
        targets=[{
            "subject_type": "student", "subject_ref": person.id,
            "consent_ref": "test-authorized-record",
        } for person in students], actor="creator",
    )
    assert staged["created"] == 30
    await core.transition_campaign(
        db_session, tenant_id=org.id, campaign_id=campaign_id,
        actor="approver", target="approved",
        authorization_ref="institutional-evidence",
    )
    await core.transition_campaign(
        db_session, tenant_id=org.id, campaign_id=campaign_id,
        actor="approver", target="running",
    )

    async def claim(owner):
        async with AsyncSessionLocal() as session:
            return await claim_batch(session, org.id, owner, limit=15)

    results = await asyncio.gather(claim("worker-a"), claim("worker-b"))
    ids = [str(item["id"]) for subset in results for item in subset]
    assert len(ids) == len(set(ids)) == 30


@pytest.mark.asyncio
async def test_individual_intervention_with_preapproved_template_is_idempotent(db_session, tenant):
    from app.models.student import Student, UploadBatch
    from app.services import dispatch_core as core
    from app.services import dispatch_interventions as interventions

    org,_ = tenant
    batch=UploadBatch(
        tenant_id=org.id,filename="one-to-one.csv",
        original_filename="one-to-one.csv",status="processed",
    )
    db_session.add(batch)
    await db_session.flush()
    student=Student(
        tenant_id=org.id,batch_id=batch.id,matricula="IND-001",
        nome="Aluno de teste",email="single@example.test",
        communication_preferences={"channels":{"email":True},"topics":{"retention":True}},
    )
    db_session.add(student)
    await db_session.commit()
    await seed_authorizations(db_session,org.id,[student.id],"individual-evidence-001")
    template=await interventions.create_template(
        db_session,tenant_id=org.id,actor="creator",
        code="retention-one-to-one",purpose="retention",
        channel="email",subject="Aviso de permanência",
        body="Olá {nome}, nossa equipe está disponível.",
    )
    with pytest.raises(ValueError,match="pessoa diferente"):
        await interventions.approve_template(
            db_session,tenant_id=org.id,actor="creator",
            template_id=str(template["id"]),evidence_ref="approval-record-01",
        )
    await interventions.approve_template(
        db_session,tenant_id=org.id,actor="approver",
        template_id=str(template["id"]),evidence_ref="approval-record-01",
    )
    first=await interventions.create_intervention(
        db_session,tenant_id=org.id,actor="creator",
        template_id=str(template["id"]),subject_type="student",
        subject_ref=student.id,evidence_ref="individual-evidence-001",
        idempotency_key="message-request-001",
    )
    assert first["status"]=="running" and first["deduplicated"] is False
    duplicate=await interventions.create_intervention(
        db_session,tenant_id=org.id,actor="creator",
        template_id=str(template["id"]),subject_type="student",
        subject_ref=student.id,evidence_ref="individual-evidence-001",
        idempotency_key="message-request-001",
    )
    assert duplicate["id"]==first["id"]
    assert duplicate["deduplicated"] is True
    with pytest.raises(ValueError,match="Idempotency-Key"):
        await interventions.create_intervention(
            db_session,tenant_id=org.id,actor="creator",
            template_id=str(template["id"]),subject_type="student",
            subject_ref=student.id,evidence_ref="other-evidence-999",
            idempotency_key="message-request-001",
        )
    await core.bind_tenant(db_session,org.id)
    number=(await db_session.execute(text("""
        SELECT count(*) FROM dispatch_items WHERE tenant_id=:tenant
          AND campaign_id=:id
    """),{"tenant":org.id,"id":first["id"]})).scalar_one()
    assert number==1


@pytest.mark.asyncio
async def test_contact_revocation_is_permanent_until_new_explicit_evidence(db_session,tenant):
    from app.services.dispatch_interventions import sync_authorization,verified_authorization

    org,_=tenant
    now=datetime.now(timezone.utc)
    kwargs={
        "db":db_session,"tenant_id":org.id,"source":"test_registry",
        "subject_type":"student","subject_ref":"unit-subject",
        "channel":"email","purpose":"retention",
        "evidence_ref":"permission-evidence-1",
        "expires_at":now+timedelta(days=7),
    }
    grant=await sync_authorization(status="granted",verified_at=now,**kwargs)
    assert grant["accepted"]
    assert await verified_authorization(
        db_session,tenant_id=org.id,subject_type="student",
        subject_ref="unit-subject",channel="email",purpose="retention",
        evidence_ref="permission-evidence-1",
    )
    revoke=await sync_authorization(status="revoked",verified_at=now+timedelta(seconds=1),**kwargs)
    assert revoke["accepted"]
    assert not await verified_authorization(
        db_session,tenant_id=org.id,subject_type="student",
        subject_ref="unit-subject",channel="email",purpose="retention",
        evidence_ref="permission-evidence-1",
    )
    with pytest.raises(ValueError,match="anterior"):
        await sync_authorization(status="granted",verified_at=now,**kwargs)


@pytest.mark.asyncio
async def test_workspace_provider_credentials_are_encrypted_and_separated(db_session, tenant_factory, monkeypatch):
    from cryptography.fernet import Fernet
    from app.core.config import get_settings
    from app.services import dispatch_providers as providers

    a,_=await tenant_factory("provider-a","Provider A")
    b,_=await tenant_factory("provider-b","Provider B")
    monkeypatch.setattr(get_settings(),"dispatch_provider_encryption_key",
                        Fernet.generate_key().decode())
    raw={
        "api_key":"re_key-for-example",
        "from_email":"message@example.test",
        "webhook_secret":"whsec_for-example",
    }
    first=await providers.configure_provider(
        db_session,tenant_id=a.id,provider="resend",actor="admin-a",data=raw,
    )
    assert first["status"]=="disabled"
    # Another tenant must never read secrets, even with the same provider name.
    assert await providers.load_provider(
        db_session,tenant_id=b.id,provider="resend",require_active=False,
    ) is None
    assert await providers.load_provider(
        db_session,tenant_id=a.id,provider="resend",require_active=False,
    )==raw
    from app.services.dispatch_core import bind_tenant
    await bind_tenant(db_session,a.id)
    cipher=(await db_session.execute(text("""
        SELECT credentials_ciphertext FROM dispatch_provider_accounts
        WHERE tenant_id=:tenant
    """),{"tenant":a.id})).scalar_one()
    assert "re_key-for-example" not in cipher
    assert "whsec_for-example" not in cipher


@pytest.mark.asyncio
async def test_dispatch_source_registry_uses_existing_workspace_connections(
    db_session, tenant_factory, monkeypatch,
):
    """Composio is metadata-only: account + toolkit policy + tenant are required."""
    from types import SimpleNamespace
    from app.models.composio_connection import (
        TenantComposioAccount, TenantComposioToolkitPolicy,
    )
    from app.models.jacad_connection import TenantJacadConnection
    from app.models.student import UploadBatch
    from app.services import dispatch_sources as sources

    tenant_a, _ = await tenant_factory("dispatch-source-a", "Source A")
    tenant_b, _ = await tenant_factory("dispatch-source-b", "Source B")
    settings = SimpleNamespace(
        composio_enabled=True, composio_api_key="test-not-real",
        composio_identity_secret="x" * 40,
        composio_allowed_toolkits="gmail",
        composio_tool_execution_enabled=False,
    )
    monkeypatch.setattr(sources, "get_settings", lambda: settings)

    batch = UploadBatch(
        tenant_id=tenant_a.id, filename="local.csv", original_filename="local.csv",
        status="processed",
    )
    db_session.add(batch)
    account = TenantComposioAccount(
        tenant_id=tenant_a.id, toolkit_slug="gmail",
        connected_account_id="test-connected-account-a",
        status="active", display_name="Workspace Gmail",
    )
    policy = TenantComposioToolkitPolicy(
        tenant_id=tenant_a.id, toolkit_slug="gmail",
        is_enabled=True, tool_slugs=["GMAIL_LIST_MESSAGES", "GMAIL_SEND_EMAIL"],
    )
    native = TenantJacadConnection(
        tenant_id=tenant_a.id, base_url="https://example.test",
        encrypted_api_token="test-secret-encrypted", status="configured",
        is_enabled=True, last_tested_at=datetime.now(timezone.utc),
    )
    db_session.add_all([account, policy, native])
    await db_session.commit()
    await db_session.refresh(batch)

    valid = await sources.require_source(
        db_session, tenant_id=tenant_a.id, kind="composio",
        reference="test-connected-account-a", tool_slug="GMAIL_LIST_MESSAGES",
    )
    assert valid.available
    assert not (await sources.require_source(
        db_session, tenant_id=tenant_b.id, kind="composio",
        reference="test-connected-account-a", tool_slug="GMAIL_LIST_MESSAGES",
    )).available
    assert not (await sources.require_source(
        db_session, tenant_id=tenant_a.id, kind="composio",
        reference="test-connected-account-a", tool_slug="GMAIL_SEND_EMAIL",
    )).available
    assert (await sources.require_source(
        db_session, tenant_id=tenant_a.id, kind="native",
        reference="jacad",
    )).available
    assert not (await sources.require_source(
        db_session, tenant_id=tenant_b.id, kind="native",
        reference="jacad",
    )).available
    assert (await sources.require_source(
        db_session, tenant_id=tenant_a.id, kind="manual",
        reference=batch.id,
    )).available
    assert not (await sources.require_source(
        db_session, tenant_id=tenant_b.id, kind="manual",
        reference=batch.id,
    )).available
    catalog = await sources.list_sources(db_session, tenant_id=tenant_a.id)
    assert not catalog["composio_tool_execution_enabled"]
    linked = [item for item in catalog["items"] if item["kind"] == "composio"]
    assert len(linked) == 1
    assert linked[0]["can_bind"]
    assert linked[0]["tools"] == ["GMAIL_LIST_MESSAGES"]
    assert linked[0]["automatic_ingestion"] is False
    assert "test-secret-encrypted" not in str(catalog)

    account.status = "revoked"
    await db_session.commit()
    assert not (await sources.require_source(
        db_session, tenant_id=tenant_a.id, kind="composio",
        reference="test-connected-account-a", tool_slug="GMAIL_LIST_MESSAGES",
    )).available


@pytest.mark.asyncio
async def test_approved_mira_proposal_reuses_governance_and_unique_outbox(
    db_session, tenant,
):
    from app.models.student import Student, UploadBatch
    from app.models.retention_campaign import RetentionCampaignProposal
    from app.services.campaign_proposals import hash_audience_snapshot
    from app.services.dispatch_proposals import materialize_proposal
    from app.services.dispatch_sources import require_source
    from app.services.dispatch_core import bind_tenant

    org, _ = tenant
    batch = UploadBatch(
        tenant_id=org.id, filename="retention.csv",
        original_filename="retention.csv", status="processed",
    )
    db_session.add(batch)
    await db_session.flush()
    student = Student(
        tenant_id=org.id, batch_id=batch.id,
        matricula="BRIDGE-001", nome="Ana", email="ana@example.test",
        communication_preferences={
            "channels": {"email": True},
            "topics": {"retention": True},
        },
    )
    db_session.add(student)
    await db_session.flush()

    snapshot = [{
        "student_id": student.id,
        "matched_group_ids": ["risk_increase"],
        "eligible_channels": ["email"],
        "blocked_reasons": [],
        "internal_action_only": False,
    }]
    checksum = hash_audience_snapshot(snapshot)
    now = datetime.now(timezone.utc)
    proposal = RetentionCampaignProposal(
        tenant_id=org.id, status="approved",
        title="Permanência — alunos com risco",
        source_group_ids=["risk_increase"],
        source_catalog_version="2026", recommendation_engine="test",
        source_evaluated_at=now, objective="Reduzir evasão",
        strategy="Contato autorizado", recommended_channels=["email"],
        cadence_days=[0], message_brief="Acompanhamento acadêmico",
        audience_snapshot=snapshot, audience_hash=checksum,
        audience_total=1, outreach_eligible_count=1, blocked_count=0,
        internal_action_count=0, created_by="creator-a", approved_by="reviewer-b",
        approved_at=now, authorization_status="institution_attested",
        authorization_basis="institutional_test_policy",
        authorization_reference="institutional-evidence-2026",
        authorization_attested_by="reviewer-b",
        authorization_attested_at=now,
    )
    db_session.add(proposal)
    await db_session.commit()
    await db_session.refresh(proposal)
    await seed_authorizations(
        db_session, org.id, [student.id], "student-retention-basis",
    )
    await bind_tenant(db_session, org.id)
    template_id = str(uuid4())
    await db_session.execute(text("""
        INSERT INTO dispatch_approved_templates (
            id,tenant_id,code,purpose,channel,subject,body,
            status,created_by,approved_by,approved_at
        ) VALUES (
            :id,:tenant,'retention-approved','retention','email',
            'Acompanhamento acadêmico','Olá {nome}, podemos ajudar?',
            'approved','template-author','template-approver',now()
        )
    """), {"id": template_id, "tenant": org.id})
    await db_session.commit()

    first = await materialize_proposal(
        db_session, tenant_id=org.id, actor="operator-c",
        proposal_id=proposal.id, template_id=template_id,
    )
    assert first["status"] == "approved"
    assert first["selected_count"] == 1
    assert not first["deduplicated"]
    repeated = await materialize_proposal(
        db_session, tenant_id=org.id, actor="operator-c",
        proposal_id=proposal.id, template_id=template_id,
    )
    assert repeated["id"] == first["id"]
    assert repeated["deduplicated"]
    await bind_tenant(db_session, org.id)
    row = (await db_session.execute(text("""
        SELECT source_kind,origin_proposal_id,origin_snapshot_hash,
               approved_by,status FROM dispatch_campaigns
        WHERE tenant_id=:tenant AND id=:id
    """), {"tenant": org.id, "id": first["id"]})).mappings().one()
    assert row["source_kind"] == "retention_proposal"
    assert str(row["origin_proposal_id"]) == proposal.id
    assert row["origin_snapshot_hash"] == checksum
    assert row["approved_by"] == "reviewer-b"
    assert (await db_session.execute(text("""
        SELECT count(*) FROM dispatch_items WHERE tenant_id=:tenant AND campaign_id=:id
    """), {"tenant": org.id, "id": first["id"]})).scalar_one() == 1
    state = await require_source(
        db_session, tenant_id=org.id, kind="retention_proposal",
        reference=proposal.id, snapshot_hash=checksum,
    )
    assert state.available

    proposal.status = "changes_requested"
    await db_session.commit()
    state = await require_source(
        db_session, tenant_id=org.id, kind="retention_proposal",
        reference=proposal.id, snapshot_hash=checksum,
    )
    assert not state.available


@pytest.mark.asyncio
async def test_retention_proposal_bridge_denies_unapproved_or_cross_tenant(
    db_session, tenant_factory,
):
    from app.services.dispatch_proposals import materialize_proposal
    from app.services.dispatch_sources import require_source

    a, _ = await tenant_factory("bridge-a", "Bridge A")
    b, _ = await tenant_factory("bridge-b", "Bridge B")
    assert not (await require_source(
        db_session, tenant_id=a.id, kind="retention_proposal",
        reference="00000000-0000-0000-0000-000000000001",
        snapshot_hash="0" * 64,
    )).available
    with pytest.raises(LookupError):
        await materialize_proposal(
            db_session, tenant_id=b.id, actor="reviewer",
            proposal_id="00000000-0000-0000-0000-000000000001",
            template_id="00000000-0000-0000-0000-000000000002",
        )


@pytest.mark.asyncio
async def test_signed_authorization_ingress_denies_unsigned_and_replayed_payloads(
    client,db_session,tenant,
):
    from app.services import dispatch_interventions as interventions
    from app.services import dispatch_core as core
    from app.services.dispatch_ingress_security import signature
    import json
    import time

    org,key=tenant
    secret=await source_test_secret(
        db_session,org.id,"test_registry","authorization",
    )
    observed=datetime.now(timezone.utc)
    body={
        "source":"test_registry","subject_type":"student",
        "subject_ref":"opaque-test-person","purpose":"retention",
        "channel":"email","evidence_ref":"consent-approved-0001",
        "status":"granted","verified_at":observed.isoformat(),
        "expires_at":(observed+timedelta(days=7)).isoformat(),
    }
    path="/api/v1/dispatch/integrations/authorizations"
    unsigned=await client.post(path,json=body,headers={"X-API-Key":key})
    assert unsigned.status_code==401
    accepted=await signed_post(client,key,"test_registry",secret,path,body)
    assert accepted.status_code==200,accepted.text
    assert accepted.json()["accepted"]
    await core.bind_tenant(db_session,org.id)
    assert await interventions.verified_authorization(
        db_session,tenant_id=org.id,subject_type="student",
        subject_ref="opaque-test-person",channel="email",
        purpose="retention",evidence_ref="consent-approved-0001",
    )
    raw=json.dumps(body,separators=(",",":"),ensure_ascii=False).encode()
    stamp=str(int(time.time()))
    nonce="a-replay-protected-nonce-0001"
    headers={
        "X-API-Key":key,"Content-Type":"application/json",
        "X-Mira-Source":"test_registry","X-Mira-Timestamp":stamp,
        "X-Mira-Nonce":nonce,
        "X-Mira-Signature":signature(
            secret,stamp,nonce,"POST",path,raw,
        ),
    }
    first=await client.post(path,content=raw,headers=headers)
    assert first.status_code==200,first.text
    replay=await client.post(path,content=raw,headers=headers)
    assert replay.status_code==409
    wrong=await client.post(
        path,content=raw,headers={**headers,"X-Mira-Nonce":"changed-nonce-but-old-signature"},
    )
    assert wrong.status_code==401


def test_composio_source_tool_binding_is_read_only():
    from app.services.dispatch_sources import source_tool_is_read_only
    assert source_tool_is_read_only("GMAIL_LIST_MESSAGES")
    assert source_tool_is_read_only("HUBSPOT_SEARCH_CONTACTS")
    assert not source_tool_is_read_only("GMAIL_SEND_EMAIL")
    assert not source_tool_is_read_only("STRIPE_CREATE_CHARGE")
    assert not source_tool_is_read_only("GMAIL_GET_AND_DELETE_MESSAGE")


@pytest.mark.asyncio
async def test_worker_eligibility_blocks_revoked_composio_source_before_provider(
    db_session, tenant, monkeypatch,
):
    from app.services import dispatch_delivery, dispatch_sources

    org, _ = tenant
    async def revoked_source(*args, **kwargs):
        return dispatch_sources.SourceState(False, "composio_account_not_active")
    monkeypatch.setattr(dispatch_sources, "require_source", revoked_source)
    decision = await dispatch_delivery.eligibility(
        db_session, tenant_id=org.id,
        campaign={
            "status": "running", "approved_at": datetime.now(timezone.utc),
            "authorization_ref": "institutional-evidence",
            "purpose": "service", "channel": "email",
            "source_kind": "composio",
            "source_ref": "revoked-account",
            "source_tool_slug": "GMAIL_LIST_MESSAGES",
            "origin_snapshot_hash": None,
        },
        item={"subject_type": "external", "subject_ref": "irrelevant"},
    )
    assert not decision.allowed
    assert decision.reason == "campaign_source_not_authorized"
