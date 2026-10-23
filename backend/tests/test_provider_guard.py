"""Testes das proteções operacionais e da idempotência distribuída."""
from __future__ import annotations

import pytest

from app.services import provider_guard


class FakeRedis:
    def __init__(self):
        self.values: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    async def set(self, key, value, *, ex=None, nx=False):
        if nx and key in self.values:
            return None
        self.values[key] = str(value)
        if ex is not None:
            self.ttls[key] = ex
        return True

    async def get(self, key):
        return self.values.get(key)

    async def delete(self, *keys):
        deleted = 0
        for key in keys:
            if key in self.values:
                del self.values[key]
                self.ttls.pop(key, None)
                deleted += 1
        return deleted

    async def aclose(self):
        return None


@pytest.mark.asyncio
async def test_distributed_message_claim_uses_atomic_set_nx(monkeypatch):
    redis = FakeRedis()
    monkeypatch.setattr(provider_guard, "redis_client", lambda: redis)
    first = await provider_guard.claim_message_send(
        tenant_id="tenant-1", idempotency_key="message-abc", ttl_seconds=600
    )
    concurrent = await provider_guard.claim_message_send(
        tenant_id="tenant-1", idempotency_key="message-abc", ttl_seconds=600
    )
    assert first is True
    assert concurrent is False
    assert next(iter(redis.ttls.values())) == 600

    await provider_guard.finish_message_send(
        tenant_id="tenant-1", idempotency_key="message-abc", state="failed"
    )
    retry_after_definitive_failure = await provider_guard.claim_message_send(
        tenant_id="tenant-1", idempotency_key="message-abc", ttl_seconds=600
    )
    assert retry_after_definitive_failure is True


def test_provider_rate_limit_is_reduced_under_backpressure():
    assert provider_guard.effective_provider_limit(
        120, backpressure_active=True, factor=0.5
    ) == 60
    assert provider_guard.effective_provider_limit(
        120, backpressure_active=False, factor=0.5
    ) == 120
    assert provider_guard.effective_provider_limit(
        1, backpressure_active=True, factor=0.1
    ) == 1
