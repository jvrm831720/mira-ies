from __future__ import annotations

import pytest

from app.agents.providers.whatsapp_dispatch import (
    selected_whatsapp_provider,
    whatsapp_provider_configured,
)
from app.agents.providers.waha import send_whatsapp_waha
from app.core.config import get_settings


@pytest.mark.asyncio
async def test_waha_text_request_uses_documented_endpoint_and_auth(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "whatsapp_provider", "waha")
    monkeypatch.setattr(settings, "waha_api_url", "https://waha.example.test/")
    monkeypatch.setattr(settings, "waha_api_key", "not-a-real-key")
    monkeypatch.setattr(settings, "waha_session", "mira-test")
    monkeypatch.setattr("app.agents.providers.waha.get_settings", lambda: settings)
    captured: dict = {}

    class Response:
        def raise_for_status(self):
            return None

        @staticmethod
        def json():
            return {"id": "waha-message-123"}

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, url, *, json, headers):
            captured.update(url=url, payload=json, headers=headers)
            return Response()

    monkeypatch.setattr("app.agents.providers.waha.httpx.AsyncClient", FakeClient)
    result = await send_whatsapp_waha(
        to="+55 (11) 98765-4321", message="código teste", idempotency_key="otp-test"
    )

    assert result.ok
    assert result.provider == "waha"
    assert result.external_id == "waha-message-123"
    assert captured["url"] == "https://waha.example.test/api/sendText"
    assert captured["payload"] == {
        "session": "mira-test",
        "chatId": "5511987654321@c.us",
        "text": "código teste",
    }
    assert captured["headers"]["X-Api-Key"] == "not-a-real-key"
    assert captured["headers"]["Idempotency-Key"] == "otp-test"


def test_selected_whatsapp_provider_requires_its_own_credentials(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "whatsapp_provider", "waha")
    monkeypatch.setattr(settings, "waha_api_url", "https://waha.example.test")
    monkeypatch.setattr(settings, "waha_api_key", "test-key")
    monkeypatch.setattr(settings, "evolution_api_url", None)
    monkeypatch.setattr(settings, "evolution_api_key", None)

    assert selected_whatsapp_provider(settings) == "waha"
    assert whatsapp_provider_configured(settings)

    monkeypatch.setattr(settings, "waha_api_key", None)
    assert not whatsapp_provider_configured(settings)
