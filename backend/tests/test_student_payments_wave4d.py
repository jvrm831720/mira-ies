"""Wave 4D-A: sandbox-only payments, multiple Composio accounts and tenant boundaries."""
import hashlib
import hmac
import json
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models.composio_connection import TenantComposioAccount
from app.models.finance_reconciliation import FinanceSourceProfile, FinanceIngestionBatch, FinanceObservation
from app.models.student import Student, UploadBatch
from app.models.student_payments import PaymentProviderProfile, StudentPaymentEvidence
from app.services import student_payments as payments


def configure(monkeypatch, *, payments_on=True, webhooks_on=True):
    monkeypatch.setattr(payments, "get_settings", lambda: SimpleNamespace(
        native_academic_enabled=True, native_academic_services_enabled=True,
        student_finance_reconciliation_enabled=True,
        student_payments_sandbox_enabled=payments_on,
        student_payments_sandbox_webhooks_enabled=webhooks_on,
        student_payments_sandbox_hmac_secret="testing-only-hmac-secret-" + "x" * 48,
    ))


def test_payment_feature_fails_closed(monkeypatch):
    configure(monkeypatch, payments_on=False)
    with pytest.raises(payments.PaymentDenied):
        payments.enabled()
    with pytest.raises(payments.PaymentDenied):
        payments.signed_sandbox_event(b"{}", "1793923200", "sha256=" + "0" * 64,
                                      str(uuid4()), str(uuid4()))


def test_amount_not_based_on_caller_input():
    source = SimpleNamespace(currency="BRL", canonical_state="partially_paid",
                             amount=Decimal("150.75"), paid_amount=Decimal("50.25"))
    assert payments.draft_amount(source) == Decimal("100.50")
    source.canonical_state = "reported_paid"
    with pytest.raises(payments.PaymentDenied):
        payments.draft_amount(source)
    source.canonical_state = "unknown"
    with pytest.raises(payments.PaymentDenied):
        payments.draft_amount(source)


@pytest.mark.parametrize("methods", [["card"], ["pix","pix"], [], ["pix","boleto","card"]])
def test_provider_metadata_rejects_unsupported_methods(methods):
    with pytest.raises(payments.PaymentDenied):
        payments.validate_provider("Test provider", "composio", "xero", methods)


def make_event_signature(raw, tenant_id, provider_id, timestamp):
    secret = ("testing-only-hmac-secret-" + "x" * 48).encode()
    scoped = hmac.new(secret, f"mira:sandbox:{tenant_id}:{provider_id}".encode(), hashlib.sha256).digest()
    mac = hmac.new(scoped, b"v1:" + timestamp.encode() + b":" + raw, hashlib.sha256).hexdigest()
    return "sha256=" + mac


def test_sandbox_envelope_authenticity_and_replay_window(monkeypatch):
    configure(monkeypatch)
    tid, pid = str(uuid4()), str(uuid4())
    raw = b'{"event":"synthetic"}'
    stamp = str(int(datetime.now(timezone.utc).timestamp()))
    signature = make_event_signature(raw, tid, pid, stamp)
    payments.signed_sandbox_event(raw, stamp, signature, tid, pid)
    with pytest.raises(payments.PaymentDenied, match="Assinatura"):
        payments.signed_sandbox_event(raw + b" ", stamp, signature, tid, pid)
    with pytest.raises(payments.PaymentDenied, match="Timestamp"):
        payments.signed_sandbox_event(raw, "1", signature, tid, pid)
    with pytest.raises(payments.PaymentDenied, match="Assinatura"):
        payments.signed_sandbox_event(raw, stamp, "sha256=" + "0" * 64, tid, pid)
    other_provider = str(uuid4())
    with pytest.raises(payments.PaymentDenied):
        payments.signed_sandbox_event(raw, stamp, signature, tid, other_provider)


def test_reject_forged_event_payloads():
    base = {
        "event_id": "evt-test", "intent_id": str(uuid4()),
        "account_id": "account-1", "state": "paid_reported",
        "amount": "20.00", "currency": "BRL",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
    }
    payload = dict(base, settlement_confirmed=True)
    with pytest.raises(payments.PaymentDenied):
        payments.normalize_event(json.dumps(payload).encode())
    payload = dict(base, state=["paid_reported"])
    with pytest.raises(payments.PaymentDenied):
        payments.normalize_event(json.dumps(payload).encode())
    payload = dict(base, currency="USD")
    with pytest.raises(payments.PaymentDenied):
        payments.normalize_event(json.dumps(payload).encode())
    normalized = payments.normalize_event(json.dumps(base).encode())
    assert normalized["state"] == "paid_reported"
    assert normalized["amount"] == Decimal("20.00")


async def make_source(db, factory, slug, user_id, *, account="xero-test-account"):
    tenant, _ = await factory(slug, slug)
    upload = UploadBatch(tenant_id=tenant.id, filename="synthetic.csv",
                         original_filename="synthetic.csv", status="completed")
    db.add(upload)
    await db.flush()
    student = Student(tenant_id=tenant.id, batch_id=upload.id, matricula="S001",
                      nome="Sandbox Student", is_active=True)
    db.add(student)
    source = FinanceSourceProfile(
        tenant_id=tenant.id, name="Connected accounting", source_kind="composio",
        connected_account_id=account, tool_slug="XERO_LIST_INVOICES", rows_path="items",
        field_map={"external_id":"id"}, status_map={"open":"open"},
        review_workflow={}, student_lookup="mira_id", enabled=True,
        mapping_version=1, created_by=user_id,
    )
    db.add(source)
    connection = TenantComposioAccount(
        tenant_id=tenant.id, toolkit_slug="xero", connected_account_id=account, status="active",
    )
    db.add(connection)
    await db.flush()
    batch = FinanceIngestionBatch(
        tenant_id=tenant.id, profile_id=source.id, actor_id=user_id,
        origin="composio", idempotency_key="synthetic-observation-batch",
        payload_digest="f" * 64, mapping_version=1,
        row_count=1, imported_count=1, unchanged_count=0,
    )
    db.add(batch)
    await db.flush()
    obs = FinanceObservation(
        tenant_id=tenant.id, profile_id=source.id, student_id=student.id,
        batch_id=batch.id, external_id="invoice-2026-001", correlation_key="contract-1",
        fingerprint="a" * 64, label="Mensalidade",
        amount=Decimal("100.00"), paid_amount=Decimal("0.00"),
        currency="BRL", canonical_state="open", raw_status="ABERTO",
        mapping_version=1,
    )
    db.add(obs)
    await db.commit()
    return tenant.id, source.id, student.id, obs.id


@pytest.mark.asyncio
async def test_workspace_composio_multiple_profiles_and_idempotent_drafts(
    db_session, tenant_factory, monkeypatch,
):
    configure(monkeypatch)
    actor = str(uuid4())
    tenant, source, student, observation = await make_source(
        db_session, tenant_factory, "sandbox-pay-a", actor, account="account-payment-A",
    )
    first = await payments.create_provider(
        db_session, tenant_id=tenant, user_id=actor, source_id=source,
        name="Sandbox ERP A", kind="composio", slug="xero", methods=["pix", "boleto"],
    )
    assert not first.enabled
    first = await payments.change_provider_enabled(
        db_session, tenant_id=tenant, provider_id=first.id,
        expected_revision=1, value=True,
    )
    second = await payments.create_provider(
        db_session, tenant_id=tenant, user_id=actor, source_id=source,
        name="Sandbox ERP B", kind="composio", slug="xero", methods=["pix"],
    )
    second = await payments.change_provider_enabled(
        db_session, tenant_id=tenant, provider_id=second.id,
        expected_revision=1, value=True,
    )
    key = "draft-2026-0000001"
    draft = await payments.create_draft(
        db_session, tenant_id=tenant, user_id=actor, provider_id=first.id,
        observation_id=observation, method="pix", idempotency_key=key,
    )
    assert draft["status"] == "draft" and draft["amount"] == "100.00"
    assert draft["pix_code"] is None and draft["settlement_confirmed"] is False
    again = await payments.create_draft(
        db_session, tenant_id=tenant, user_id=actor, provider_id=first.id,
        observation_id=observation, method="pix", idempotency_key=key,
    )
    assert again["deduplicated"] and again["id"] == draft["id"]
    with pytest.raises(payments.PaymentDenied, match="idempotente"):
        await payments.create_draft(
            db_session, tenant_id=tenant, user_id=actor, provider_id=first.id,
            observation_id=observation, method="boleto", idempotency_key=key,
        )
    await db_session.rollback()
    separate = await payments.create_draft(
        db_session, tenant_id=tenant, user_id=actor, provider_id=second.id,
        observation_id=observation, method="pix", idempotency_key=key,
    )
    assert separate["id"] != draft["id"]


@pytest.mark.asyncio
async def test_sandbox_report_is_append_only_not_bank_settlement(
    db_session, tenant_factory, monkeypatch,
):
    configure(monkeypatch)
    actor = str(uuid4())
    tenant, source, _, obs_id = await make_source(
        db_session, tenant_factory, "sandbox-pay-b", actor, account="account-payment-B",
    )
    provider = await payments.create_provider(
        db_session, tenant_id=tenant, user_id=actor, source_id=source,
        name="Events sandbox", kind="composio", slug="xero", methods=["pix"],
    )
    provider = await payments.change_provider_enabled(
        db_session, tenant_id=tenant, provider_id=provider.id, expected_revision=1, value=True,
    )
    draft = await payments.create_draft(
        db_session, tenant_id=tenant, user_id=actor, provider_id=provider.id,
        observation_id=obs_id, method="pix", idempotency_key="sandbox-evidence-draft",
    )
    event = {
        "event_id": "sandbox-event-01", "intent_id": draft["id"],
        "account_id": "account-payment-B", "state": "paid_reported",
        "amount": "100.00", "currency": "BRL",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
    }
    raw = json.dumps(event, separators=(",", ":")).encode()
    stamp = str(int(datetime.now(timezone.utc).timestamp()))
    signature = make_event_signature(raw, tenant, provider.id, stamp)
    accepted = await payments.store_sandbox_event(
        db_session, tenant_id=tenant, provider_id=provider.id,
        raw=raw, timestamp=stamp, signature=signature,
    )
    assert accepted == {"accepted": True, "deduplicated": False, "settlement_confirmed": False}
    repeated = await payments.store_sandbox_event(
        db_session, tenant_id=tenant, provider_id=provider.id,
        raw=raw, timestamp=stamp, signature=signature,
    )
    assert repeated["deduplicated"] is True
    entries = (await db_session.execute(select(StudentPaymentEvidence).where(
        StudentPaymentEvidence.tenant_id == tenant,
        StudentPaymentEvidence.provider_id == provider.id,
    ))).scalars().all()
    assert len(entries) == 1 and entries[0].reported_state == "paid_reported"
    original = (await db_session.execute(select(FinanceObservation).where(
        FinanceObservation.tenant_id == tenant, FinanceObservation.id == obs_id,
    ))).scalar_one()
    assert original.canonical_state == "open" and original.paid_amount == Decimal("0")


@pytest.mark.asyncio
async def test_cross_tenant_provider_and_observation_rejected(
    db_session, tenant_factory, monkeypatch,
):
    configure(monkeypatch)
    actor = str(uuid4())
    tenant_a, source_a, _, obs_a = await make_source(
        db_session, tenant_factory, "sandbox-tenant-a", actor, account="account-payment-TA",
    )
    tenant_b, source_b, _, obs_b = await make_source(
        db_session, tenant_factory, "sandbox-tenant-b", actor, account="account-payment-TB",
    )
    provider = await payments.create_provider(
        db_session, tenant_id=tenant_a, user_id=actor, source_id=source_a,
        name="Tenant A PSP", kind="composio", slug="xero", methods=["pix"],
    )
    provider = await payments.change_provider_enabled(
        db_session, tenant_id=tenant_a, provider_id=provider.id, expected_revision=1, value=True,
    )
    with pytest.raises(payments.PaymentDenied, match="Obrigação"):
        await payments.create_draft(
            db_session, tenant_id=tenant_a, user_id=actor, provider_id=provider.id,
            observation_id=obs_b, method="pix", idempotency_key="isolated-tenant-draft",
        )
    await db_session.rollback()
    # The other tenant also cannot use the provider ID from tenant A.
    with pytest.raises(payments.PaymentDenied, match="Provedor"):
        await payments.create_draft(
            db_session, tenant_id=tenant_b, user_id=actor, provider_id=provider.id,
            observation_id=obs_a, method="pix", idempotency_key="isolated-other-draft",
        )
