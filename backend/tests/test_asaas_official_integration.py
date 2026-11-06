"""PostgreSQL integration: real RLS-scoped Asaas records, no provider network calls."""
from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models.asaas_live import AsaasCharge
from app.models.finance_reconciliation import (
    FinanceSourceProfile, FinanceIngestionBatch, FinanceObservation,
)
from app.models.student import Student, UploadBatch
from app.models.student_payments import AsaasWorkspaceDestination
from app.services import asaas_live as live
from app.services import asaas_gateway as gateway
from app.services.dispatch_core import bind_tenant


async def setup(db, factory, slug, actor):
    tenant, _ = await factory(slug, slug)
    upload = UploadBatch(tenant_id=tenant.id, filename="synthetic.csv",
                         original_filename="synthetic.csv", status="completed")
    db.add(upload)
    await db.flush()
    student = Student(tenant_id=tenant.id, batch_id=upload.id,
                      matricula="A-2026", nome="Test Student",
                      is_active=True, custom_fields={"billing_cpf": "52998224725"})
    db.add(student)
    sources = []
    for name in ("ERP-1", "ERP-2"):
        source = FinanceSourceProfile(
            tenant_id=tenant.id, name=name, source_kind="import",
            connected_account_id=None, tool_slug=None,
            rows_path="", field_map={"external_id":"id"},
            status_map={"open":"open"}, review_workflow={},
            student_lookup="mira_id", enabled=True,
            mapping_version=1, created_by=actor,
        )
        db.add(source)
        sources.append(source)
    db.add(AsaasWorkspaceDestination(
        tenant_id=tenant.id, wallet_id=str(uuid4()),
        status="pending", confirmed_by_user_id=actor,
    ))
    await db.flush()
    observations = []
    for source, external in zip(sources, ("erp1-identifier", "erp2-identifier")):
        batch = FinanceIngestionBatch(
            tenant_id=tenant.id, profile_id=source.id,
            actor_id=actor, origin="import", idempotency_key="import-" + external,
            payload_digest="e"*64, mapping_version=1,
            row_count=1, imported_count=1, unchanged_count=0,
        )
        db.add(batch)
        await db.flush()
        observation = FinanceObservation(
            tenant_id=tenant.id, profile_id=source.id,
            student_id=student.id, batch_id=batch.id,
            external_id=external, correlation_key="same-monthly-debt",
            fingerprint=external.ljust(64, "f"), label="Monthly fee",
            amount=Decimal("120.00"), paid_amount=Decimal("20.00"),
            currency="BRL", canonical_state="partially_paid",
            raw_status="PARTIAL", mapping_version=1,
        )
        db.add(observation)
        observations.append(observation)
    await db.commit()
    return str(tenant.id), [str(s.id) for s in sources], [str(o.id) for o in observations]


def patch_provider(monkeypatch):
    monkeypatch.setattr(gateway, "environment", lambda **kwargs: "sandbox")
    monkeypatch.setattr(gateway, "issuer_wallet", lambda: str(uuid4()))
    async def customer(**kwargs):
        return "cus_1000000000"
    monkeypatch.setattr(gateway, "get_or_create_customer", customer)


@pytest.mark.asyncio
async def test_one_charge_even_with_two_import_sources_and_no_real_post(
    db_session, tenant_factory, monkeypatch,
):
    patch_provider(monkeypatch)
    actor = str(uuid4())
    tenant, sources, obs = await setup(db_session, tenant_factory, "asaas-int-a", actor)
    today = date.today() + timedelta(days=7)
    first = await live.prepare_charge(
        db_session, tenant_id=tenant, user_id=actor,
        observation_id=obs[0], method="pix", due_date=today,
    )
    assert first["amount"] == "100.00"
    assert first["creation_state"] == "prepared"
    assert first["split_settled_verified"] is False
    with pytest.raises(live.AsaasFlowDenied, match="já possui uma cobrança"):
        await live.prepare_charge(
            db_session, tenant_id=tenant, user_id=actor,
            observation_id=obs[1], method="boleto", due_date=today,
        )
    await db_session.rollback()
    await bind_tenant(db_session, tenant)
    charges = (await db_session.execute(select(AsaasCharge).where(
        AsaasCharge.tenant_id == tenant,
    ))).scalars().all()
    assert len(charges) == 1
    assert charges[0].asaas_payment_id is None
    assert charges[0].split_settled_verified is False


@pytest.mark.asyncio
async def test_tenant_boundary_blocks_misissued_charge(
    db_session, tenant_factory, monkeypatch,
):
    patch_provider(monkeypatch)
    actor = str(uuid4())
    tenant_a, _, obs_a = await setup(db_session, tenant_factory, "asaas-int-b", actor)
    tenant_b, _, _ = await setup(db_session, tenant_factory, "asaas-int-c", actor)
    with pytest.raises(live.AsaasFlowDenied, match="não encontrada"):
        await live.prepare_charge(
            db_session, tenant_id=tenant_b, user_id=actor,
            observation_id=obs_a[0], method="pix",
            due_date=date.today() + timedelta(days=7),
        )
    await db_session.rollback()
    await bind_tenant(db_session, tenant_a)
    rows = (await db_session.execute(select(AsaasCharge).where(
        AsaasCharge.tenant_id == tenant_a,
    ))).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_provider_timeout_keeps_charge_fenced_and_never_retries(
    db_session, tenant_factory, monkeypatch,
):
    patch_provider(monkeypatch)
    actor = str(uuid4())
    tenant, _, obs = await setup(db_session, tenant_factory, "asaas-int-d", actor)
    first = await live.prepare_charge(
        db_session, tenant_id=tenant, user_id=actor,
        observation_id=obs[0], method="pix",
        due_date=date.today() + timedelta(days=7),
    )
    counter = {"posts": 0}
    issuer = gateway.issuer_wallet()
    async def fake_request(method, path, **kwargs):
        if method == "GET" and path == "/wallets/":
            return {"walletId": issuer}
        if method == "POST" and path == "/payments":
            counter["posts"] += 1
            raise gateway.GatewayInconclusive("synthetic timeout")
        raise AssertionError("Unexpected API request")
    monkeypatch.setattr(gateway, "issuer_wallet", lambda: issuer)
    monkeypatch.setattr(gateway, "request", fake_request)
    with pytest.raises(live.AsaasFlowDenied, match="inconclusiva"):
        await live.submit_charge(db_session, tenant_id=tenant, charge_id=first["id"], user_id=actor)
    await db_session.rollback()
    record = await live.get_charge(db_session, tenant, first["id"])
    assert record.creation_state == "unknown"
    assert record.reconciliation_required
    with pytest.raises(live.AsaasFlowDenied, match="já iniciado"):
        await live.submit_charge(db_session, tenant_id=tenant, charge_id=first["id"], user_id=actor)
    assert counter["posts"] == 1
