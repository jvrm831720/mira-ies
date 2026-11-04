from datetime import datetime, timezone
import json

import httpx
import pytest

from app.services.connectors.isaac_marlim_api import (
    IsaacMarlimApiClient,
    IsaacMarlimAuthenticationError,
    IsaacMarlimConfig,
    IsaacMarlimContractError,
)


def _response(request: httpx.Request) -> httpx.Response:
    assert request.method == "POST"
    assert request.url.host == "sandbox.api.marlim.co"
    assert request.url.path == "/v3/conciliation"
    assert request.headers["api_key"] == "sandbox-test-key"
    assert json.loads(request.read()) == {
        "date_created": "2026-11-04T12:00:00Z",
        "with_transactions": True,
        "page": 2,
        "count": 50,
    }
    return httpx.Response(200, json={
        "transfer_reference_date": "2026-11-04",
        "paid_transactions_amount": 12500,
        "refunded_transactions_amount": 2500,
        "transfer_estimated_amount": 10000,
        "paid_transactions": [{
            "transaction_id": "tx-1",
            "item_id": "mira-charge-1",
            "paid_amount": 12500,
            "date_created": "2026-11-04T11:00:00.000Z",
            "date_updated": "2026-11-04T11:01:00.000Z",
            "customer_document_number": "MUST_NOT_BE_RETURNED",
            "card_first_digits": "123456",
            "card_last_digits": "1234",
        }],
        "refunded_transactions": [{
            "transaction_id": "tx-2",
            "item_id": "mira-charge-2",
            "refunded_amount": 2500,
            "date_created": "2026-11-04T10:00:00.000Z",
            "date_updated": "2026-11-04T10:05:00.000Z",
            "customer_document_number": "MUST_NOT_BE_RETURNED",
        }],
    })


@pytest.mark.asyncio
async def test_fetch_conciliation_reads_sanitized_payment_events():
    client = IsaacMarlimApiClient(
        IsaacMarlimConfig("sandbox-test-key", "sandbox"),
        transport=httpx.MockTransport(_response),
    )
    try:
        result = await client.fetch_conciliation(
            date_created=datetime(2026, 11, 4, 12, tzinfo=timezone.utc),
            page=2,
            count=50,
        )
    finally:
        await client.close()

    assert result.reference_date == "2026-11-04"
    assert result.paid_transactions_amount_cents == 12500
    assert result.refunded_transactions_amount_cents == 2500
    assert result.transfer_estimated_amount_cents == 10000
    assert [item.state for item in result.transactions] == ["paid", "refunded"]
    assert result.transactions[0].item_id == "mira-charge-1"
    assert not hasattr(result.transactions[0], "customer_document_number")


def test_config_uses_fixed_official_environment_hosts():
    assert IsaacMarlimConfig("key", "sandbox").base_url() == "https://sandbox.api.marlim.co"
    assert IsaacMarlimConfig("key", "production").base_url() == "https://api.marlim.co"


def test_config_rejects_missing_key():
    with pytest.raises(ValueError, match="API key"):
        IsaacMarlimConfig("", "sandbox").base_url()


@pytest.mark.asyncio
async def test_authentication_failure_is_sanitized():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"message": "forbidden", "secret": "do-not-leak"})

    client = IsaacMarlimApiClient(
        IsaacMarlimConfig("secret-key", "sandbox"),
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(IsaacMarlimAuthenticationError) as exc:
            await client.fetch_conciliation(
                date_created=datetime(2026, 11, 4, tzinfo=timezone.utc)
            )
    finally:
        await client.close()
    assert "do-not-leak" not in str(exc.value)


@pytest.mark.asyncio
async def test_rejects_naive_datetime_before_request():
    client = IsaacMarlimApiClient(IsaacMarlimConfig("key", "sandbox"))
    try:
        with pytest.raises(ValueError, match="timezone"):
            await client.fetch_conciliation(date_created=datetime(2026, 11, 4))
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_rejects_count_above_documented_v3_limit():
    client = IsaacMarlimApiClient(IsaacMarlimConfig("key", "sandbox"))
    try:
        with pytest.raises(ValueError, match="1000"):
            await client.fetch_conciliation(
                date_created=datetime(2026, 11, 4, tzinfo=timezone.utc),
                count=1001,
            )
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_rejects_unexpected_money_type():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "paid_transactions_amount": 1.5,
            "refunded_transactions_amount": 0,
            "transfer_estimated_amount": 0,
        })

    client = IsaacMarlimApiClient(
        IsaacMarlimConfig("key", "sandbox"),
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(IsaacMarlimContractError):
            await client.fetch_conciliation(
                date_created=datetime(2026, 11, 4, tzinfo=timezone.utc),
                with_transactions=False,
            )
    finally:
        await client.close()
