"""Wave 4D-A: only non-executing sandbox proposals; PostgreSQL synthetic fixtures."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models.finance_reconciliation import FinanceIngestionBatch, FinanceObservation, FinanceSourceProfile
from app.models.student import Student, UploadBatch
from app.models.student_payments import StudentPaymentConnector, StudentPaymentOrder, StudentPaymentOrderEvent
from app.services import student_payments as payment


def activate(monkeypatch):
    monkeypatch.setattr(payment, "get_settings", lambda: SimpleNamespace(
        student_payment_preparation_enabled=True,
        student_finance_reconciliation_enabled=True,
        native_academic_enabled=True,
        native_academic_services_enabled=True,
    ))


def observation(*, amount="120.00", paid="20.00", state="open", currency="BRL"):
    return SimpleNamespace(amount=Decimal(amount), paid_amount=Decimal(paid),
                           canonical_state=state, currency=currency)


@pytest.mark.parametrize("state", ["unknown", "reported_paid", "cancelled", "disputed"])
def test_nonpayable_source_states_are_denied(state):
    with pytest.raises(payment.PaymentPreparationDenied):
        payment.amount_for_observation(observation(state=state))


def test_amount_cannot_be_invented_by_client_or_round_partial():
    assert payment.amount_for_observation(observation()) == Decimal("100.00")
    with pytest.raises(payment.PaymentPreparationDenied):
        payment.amount_for_observation(observation(amount="100", paid="100"))
    with pytest.raises(payment.PaymentPreparationDenied):
        payment.amount_for_observation(observation(amount="100.005", paid="0"))


def test_asaas_split_is_fixed_to_100_percent_of_net_and_requires_wallet():
    destination = str(uuid4())
    assert payment.normalize_destination_wallet(destination) == destination
    assert payment.build_asaas_charge_split(destination) == {
        "split": [{"walletId": destination, "percentualValue": 100}]
    }
    assert "fixedValue" not in payment.build_asaas_charge_split(destination)["split"][0]
    with pytest.raises(payment.PaymentPreparationDenied, match="próprio split"):
        payment.normalize_destination_wallet(destination, issuer_wallet_id=destination)
    for bad in ("", "__import__", "STRIPE", "../psp", "123456-7", str(uuid4()) + "x", "ZZZZZZZZ-ZZZZ-ZZZZ-ZZZZ-ZZZZZZZZZZZZ"):
        with pytest.raises(payment.PaymentPreparationDenied):
            payment.normalize_destination_wallet(bad)


def test_payments_disabled_by_default(monkeypatch):
    monkeypatch.setattr(payment, "get_settings", lambda: SimpleNamespace(
        student_payment_preparation_enabled=False,
        student_finance_reconciliation_enabled=True,
        native_academic_enabled=True,
        native_academic_services_enabled=True,
    ))
    with pytest.raises(payment.PaymentPreparationDenied):
        payment.require_enabled()


async def fixture_source(db_session, tenant_factory, tenant_slug):
    tenant, _ = await tenant_factory(tenant_slug, tenant_slug)
    upload = UploadBatch(tenant_id=tenant.id, filename="payments.csv",
                         original_filename="payments.csv", status="completed")
    db_session.add(upload)
    await db_session.flush()
    student = Student(tenant_id=tenant.id, batch_id=upload.id,
                      matricula="PAY001", nome="Payment Example", is_active=True)
    db_session.add(student)
    profile = FinanceSourceProfile(
        tenant_id=tenant.id, name="Finance " + tenant_slug,
        source_kind="import", connected_account_id=None, tool_slug=None,
        rows_path="", field_map={"external_id": "ref"}, status_map={"open": "open"},
        review_workflow={"transitions": {"open": []}, "labels": {"open": "Aberto"}},
        student_lookup="mira_id", enabled=True, mapping_version=1,
        created_by=str(uuid4()),
    )
    db_session.add(profile)
    await db_session.flush()
    batch = FinanceIngestionBatch(
        tenant_id=tenant.id, profile_id=profile.id, actor_id=profile.created_by,
        origin="import", idempotency_key="payment-fixture-batch-0001",
        payload_digest="f" * 64, mapping_version=1,
        row_count=1, imported_count=1, unchanged_count=0,
    )
    db_session.add(batch)
    await db_session.flush()
    obs = FinanceObservation(
        tenant_id=tenant.id, profile_id=profile.id, student_id=student.id,
        batch_id=batch.id, external_id="ERP-OBLIGATION-1",
        correlation_key="academic-month-1", fingerprint="f" * 64,
        label="Mensalidade", amount=Decimal("145.50"), paid_amount=Decimal("0"),
        currency="BRL", due_at=None, source_updated_at=None,
        canonical_state="open", raw_status="OPEN", mapping_version=1,
        observed_at=datetime.now(timezone.utc) - timedelta(minutes=3),
    )
    db_session.add(obs)
    await db_session.commit()
    return tenant.id, student.id, profile.id, obs.id


@pytest.mark.asyncio
async def test_one_asaas_destination_for_two_financial_sources_and_two_person_approval(db_session, tenant_factory, monkeypatch):
    activate(monkeypatch)
    tenant_id, student_id, profile_id, observation_id = await fixture_source(
        db_session, tenant_factory, "pay-multiple-providers",
    )
    proposer, reviewer = str(uuid4()), str(uuid4())
    connector = await payment.create_connector(
        db_session, tenant_id=tenant_id, actor_id=proposer,
        destination_wallet_id=str(uuid4()),
    )
    assert connector.mode == "sandbox" and not connector.enabled
    assert connector.provider_slug == "asaas"
    assert connector.destination_verification_status == "pending"
    assert payment.build_asaas_charge_split(connector.destination_wallet_id)["split"][0]["percentualValue"] == 100
    connector = await payment.toggle_connector(
        db_session, tenant_id=tenant_id, connector_id=connector.id,
        expected_version=1, enabled=True,
    )
    order, dedup = await payment.prepare_order(
        db_session, tenant_id=tenant_id, actor_id=proposer, connector_id=connector.id,
        observation_id=observation_id, idempotency_key="pay-one-obligation-0001",
    )
    assert not dedup and order.amount == Decimal("145.50")
    same, dedup = await payment.prepare_order(
        db_session, tenant_id=tenant_id, actor_id=proposer, connector_id=one.id,
        observation_id=observation_id, idempotency_key="pay-one-obligation-0001",
    )
    assert dedup and same.id == order.id
    # One payout wallet receives proposals from distinct financial sources.
    second_profile = FinanceSourceProfile(
        tenant_id=tenant_id, name="Another source", source_kind="composio",
        connected_account_id="sandbox-second", tool_slug="READ_ONLY",
        rows_path="data", field_map={"external_id": "id"},
        status_map={"open": "open"}, review_workflow={"transitions": {"open": []}, "labels": {"open": "Novo"}},
        student_lookup="mira_id", enabled=True, mapping_version=1, created_by=proposer,
    )
    db_session.add(second_profile)
    await db_session.flush()
    second_batch = FinanceIngestionBatch(
        tenant_id=tenant_id, profile_id=second_profile.id, actor_id=proposer,
        origin="composio", idempotency_key="payment-second-source-0001",
        payload_digest="a" * 64, mapping_version=1, row_count=1,
        imported_count=1, unchanged_count=0,
    )
    db_session.add(second_batch)
    await db_session.flush()
    second_obs = FinanceObservation(
        tenant_id=tenant_id, profile_id=second_profile.id, student_id=student_id,
        batch_id=second_batch.id, external_id="OTHER-ERP-2", correlation_key=None,
        fingerprint="a" * 64, label="Matrícula", amount=Decimal("85.00"),
        paid_amount=Decimal("0"), currency="BRL", due_at=None,
        source_updated_at=None, canonical_state="open", raw_status="OPEN", mapping_version=1,
    )
    db_session.add(second_obs)
    await db_session.commit()
    other, duplicated = await payment.prepare_order(
        db_session, tenant_id=tenant_id, actor_id=proposer, connector_id=connector.id,
        observation_id=second_obs.id, idempotency_key="pay-second-source-0001",
    )
    assert not duplicated and other.id != order.id and other.student_id == student_id
    assert other.source_profile_id != order.source_profile_id
    await payment.transition_order(db_session, tenant_id=tenant_id, order_id=order.id,
                                   actor_id=proposer, target="awaiting_approval",
                                   expected_status="draft", note="Enviar ao gestor financeiro")
    with pytest.raises(payment.PaymentPreparationDenied, match="própria proposta"):
        await payment.transition_order(db_session, tenant_id=tenant_id, order_id=order.id,
                                       actor_id=proposer, target="approved",
                                       expected_status="awaiting_approval", note="Autoaprovação proibida")
    approved = await payment.transition_order(db_session, tenant_id=tenant_id, order_id=order.id,
                                               actor_id=reviewer, target="approved",
                                               expected_status="awaiting_approval",
                                               note="Revisão manual em sandbox")
    assert approved.approved_by == reviewer
    assert payment.order_json(approved)["provider_execution_enabled"] is False
    assert payment.order_json(approved)["checkout_url"] is None
    assert payment.order_json(approved)["settlement_confirmed"] is False
    history = (await db_session.execute(select(StudentPaymentOrderEvent).where(
        StudentPaymentOrderEvent.tenant_id == tenant_id,
        StudentPaymentOrderEvent.order_id == order.id,
    ))).scalars().all()
    assert [x.status for x in history] == ["draft", "awaiting_approval", "approved"]


@pytest.mark.asyncio
async def test_foreign_tenant_obligation_never_creates_payment(db_session, tenant_factory, monkeypatch):
    activate(monkeypatch)
    foreign_tenant, _, _, foreign_observation = await fixture_source(
        db_session, tenant_factory, "pay-foreign-tenant",
    )
    my_tenant, _, _, _ = await fixture_source(
        db_session, tenant_factory, "pay-own-tenant",
    )
    actor = str(uuid4())
    connector = await payment.create_connector(
        db_session, tenant_id=my_tenant, actor_id=actor,
        destination_wallet_id=str(uuid4()),
    )
    connector = await payment.toggle_connector(db_session, tenant_id=my_tenant,
                                               connector_id=connector.id,
                                               expected_version=1, enabled=True)
    with pytest.raises(payment.PaymentPreparationDenied, match="outro perfil"):
        await payment.prepare_order(db_session, tenant_id=my_tenant, actor_id=actor,
                                    connector_id=connector.id, observation_id=foreign_observation,
                                    idempotency_key="cross-tenant-payment-0001")
    await db_session.rollback()
    rows = (await db_session.execute(select(StudentPaymentOrder).where(
        StudentPaymentOrder.tenant_id == my_tenant,
    ))).scalars().all()
    assert rows == []
    assert foreign_tenant != my_tenant
