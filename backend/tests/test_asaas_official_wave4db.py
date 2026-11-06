"""Wave 4D-B: official API contract, Split truth, webhook authentication and no retry."""
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4
import json

import pytest

from app.services import asaas_gateway as gateway
from app.services import asaas_webhooks as hooks
from app.services import asaas_live as flow


def settings(**changes):
    base = dict(
        asaas_mode="sandbox", asaas_sandbox_enabled=True,
        asaas_production_enabled=False, app_env="test",
        asaas_sandbox_api_key="sandbox_test_secret_key_" + "a" * 30,
        asaas_production_api_key="production_test_secret_key_" + "b" * 30,
        asaas_sandbox_webhook_token="synthetic-webhook-secret-" + "c" * 42,
        asaas_production_webhook_token="production-webhook-secret-" + "d" * 42,
        asaas_worker_secret="worker_test_secret_" + "e" * 40,
        student_payments_asaas_issuer_wallet_id=str(uuid4()),
        native_academic_enabled=True, native_academic_services_enabled=True,
        student_finance_reconciliation_enabled=True,
    )
    base.update(changes)
    return SimpleNamespace(**base)


def test_official_environment_is_explicit_and_fail_closed(monkeypatch):
    monkeypatch.setattr(gateway, "get_settings", lambda: settings())
    assert gateway.environment(write=True) == "sandbox"
    monkeypatch.setattr(gateway, "get_settings", lambda: settings(asaas_mode="production"))
    with pytest.raises(gateway.GatewayDenied):
        gateway.environment(write=True)
    monkeypatch.setattr(gateway, "get_settings", lambda: settings(
        asaas_mode="production", asaas_production_enabled=True, app_env="production",
    ))
    assert gateway.environment(write=True) == "production"
    monkeypatch.setattr(gateway, "get_settings", lambda: settings(
        asaas_mode="production", asaas_production_enabled=True, app_env="development",
    ))
    with pytest.raises(gateway.GatewayDenied):
        gateway.environment()


@pytest.mark.parametrize("raw", ["", "00000000000", "12345678900", "999.999.999-99", "1234567890a"])
def test_payer_cpf_fails_closed(raw):
    with pytest.raises(gateway.GatewayDenied):
        gateway.validate_cpf(raw)


def test_payer_cpf_valid():
    assert gateway.validate_cpf("529.982.247-25") == "52998224725"


def charge():
    return SimpleNamespace(
        external_reference="MIRA-" + str(uuid4()),
        customer_id="cus_000005219613", method="pix",
        amount=Decimal("100.50"), destination_wallet_id=str(uuid4()),
        asaas_payment_id="pay_123456789012",
    )


def remote(c):
    return {
        "id": c.asaas_payment_id, "externalReference": c.external_reference,
        "customer": c.customer_id, "billingType": "PIX",
        "value": 100.50,
        "split": [{"walletId": c.destination_wallet_id, "percentualValue": 100}],
        "status": "PENDING",
    }


def test_charge_payload_uses_only_single_100_percent_net_split():
    c = charge()
    body = gateway.charge_payload(
        customer_id=c.customer_id, method=c.method,
        amount=c.amount, due_date=date(2026, 11, 15),
        external_reference=c.external_reference,
        destination_wallet_id=c.destination_wallet_id,
    )
    assert body["split"] == [{"walletId": c.destination_wallet_id, "percentualValue": 100}]
    assert body["billingType"] == "PIX"
    assert body["value"] == 100.5
    assert "apiKey" not in body and "recipient" not in body
    assert gateway.verify_payment_response(remote(c), c) == c.asaas_payment_id


@pytest.mark.parametrize("change", [
    {"value": 101}, {"customer": "cus_987654321"},
    {"externalReference": "someone-else"},
    {"split": []},
    {"split": [{"walletId": str(uuid4()), "percentualValue": 100}]},
    {"split": [{"walletId": str(uuid4()), "percentualValue": 95}]},
    {"split": [{"walletId": "fake", "fixedValue": 100}]},
])
def test_remote_payment_mismatch_never_marks_as_verified(change):
    c = charge()
    payment = remote(c)
    payment.update(change)
    with pytest.raises(gateway.GatewayInconclusive):
        gateway.verify_payment_response(payment, c)


def test_split_settlement_requires_confirmed_provider_id_and_wallet():
    c = charge()
    split_id = str(uuid4())
    good = {"id": split_id, "walletId": c.destination_wallet_id,
            "payment": {"id": c.asaas_payment_id}, "status": "DONE"}
    assert gateway.verify_split_response(good, c, split_id)
    assert gateway.verify_split_response({**good, "status": "PENDING"}, c, split_id) is False
    with pytest.raises(gateway.GatewayInconclusive):
        gateway.verify_split_response({**good, "walletId": str(uuid4())}, c, split_id)
    with pytest.raises(gateway.GatewayInconclusive):
        gateway.verify_split_response({**good, "payment": {"id": "pay_other"}}, c, split_id)


def test_customer_reference_is_stable_and_tenant_opaque():
    uid = str(uuid4())
    assert gateway.customer_reference(uid) == gateway.customer_reference(uid)
    assert flow.financial_key(SimpleNamespace(
        tenant_id="t", profile_id="p", student_id="s", correlation_key="contract-1",
        external_id="a",
    )) != flow.financial_key(SimpleNamespace(
        tenant_id="t2", profile_id="p", student_id="s", correlation_key="contract-1",
        external_id="a",
    ))


@pytest.mark.asyncio
async def test_network_adapter_only_allows_pinned_routes(monkeypatch):
    monkeypatch.setattr(gateway, "get_settings", lambda: settings())
    with pytest.raises(gateway.GatewayDenied):
        await gateway.request("GET", "https://attacker.example/api")
    with pytest.raises(gateway.GatewayDenied):
        await gateway.request("GET", "/payments/../../private")
    with pytest.raises(gateway.GatewayDenied):
        await gateway.request("PATCH", "/payments/test")


def test_official_webhook_header_and_event_contract(monkeypatch):
    monkeypatch.setattr(gateway, "get_settings", lambda: settings())
    hooks.valid_token(settings().asaas_sandbox_webhook_token)
    with pytest.raises(hooks.AsaasHookDenied):
        hooks.valid_token("wrong")
    payload = {"id": "evt_0033099", "event": "PAYMENT_SPLIT_DONE",
               "payment": {"id": "pay_123456789012"},
               "additionalInfo": {"splitId": str(uuid4())}}
    parsed = hooks.parse_event(json.dumps(payload).encode())
    assert parsed["event_type"] == "PAYMENT_SPLIT_DONE"
    assert "secret" not in parsed and "student_id" not in parsed
    with pytest.raises(hooks.AsaasHookDenied):
        hooks.parse_event(json.dumps({**payload, "payment": {}}).encode())
    with pytest.raises(hooks.AsaasHookDenied):
        hooks.parse_event(json.dumps(payload).encode() + b" " * 33000)


def test_worker_requires_separate_strong_secret(monkeypatch):
    monkeypatch.setattr(hooks, "get_settings", lambda: settings())
    hooks.worker_secret_valid(settings().asaas_worker_secret)
    with pytest.raises(hooks.AsaasHookDenied):
        hooks.worker_secret_valid(settings().asaas_sandbox_webhook_token)


def test_no_double_charge_when_external_reference_is_same():
    a = SimpleNamespace(tenant_id="tenant", profile_id="src-a",
                        student_id="same", correlation_key="contract-a",
                        external_id="001")
    b = SimpleNamespace(tenant_id="tenant", profile_id="src-b",
                        student_id="same", correlation_key="contract-a",
                        external_id="other")
    assert flow.financial_key(a) == flow.financial_key(b)


def test_gateway_returns_no_directly_configurable_urls():
    assert gateway.BASES == {
        "sandbox": "https://api-sandbox.asaas.com/v3",
        "production": "https://api.asaas.com/v3",
    }
