"""Testes unitários do contrato WAHA sem chamadas de rede."""
from __future__ import annotations

from app.agents.providers import waha
from app.agents.providers import whatsapp as whatsapp_router
from app.agents.base import SendResult
from app.core.config import get_settings


async def test_waha_provider_builds_send_text_request(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "waha_api_url", "https://waha.test/")
    monkeypatch.setattr(settings, "waha_api_key", "test-api-key")
    monkeypatch.setattr(settings, "waha_session", "mira")
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"id": "waha-message-1"}

    class FakeClient:
        def __init__(self, **kwargs):
            captured["timeout"] = kwargs["timeout"]

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, *, json, headers):
            captured.update(url=url, payload=json, headers=headers)
            return FakeResponse()

    monkeypatch.setattr(waha.httpx, "AsyncClient", FakeClient)

    result = await waha.send_whatsapp_waha(
        to="+55 (21) 98181-1077",
        message="Código de teste",
        idempotency_key="test-idempotency-key",
    )

    assert result.ok is True
    assert result.provider == "waha"
    assert result.external_id == "waha-message-1"
    assert captured["url"] == "https://waha.test/api/sendText"
    assert captured["headers"]["X-Api-Key"] == "test-api-key"
    assert captured["headers"]["Idempotency-Key"] == "test-idempotency-key"
    assert captured["payload"] == {
        "session": "mira",
        "chatId": "5521981811077@c.us",
        "text": "Código de teste",
    }


async def test_whatsapp_router_prefers_waha_when_both_are_configured(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "waha_api_url", "https://waha.test")
    monkeypatch.setattr(settings, "waha_api_key", "test-waha-key")
    monkeypatch.setattr(settings, "evolution_api_url", "https://evolution.test")
    monkeypatch.setattr(settings, "evolution_api_key", "test-evolution-key")
    called = []

    async def fake_waha(**kwargs):
        called.append("waha")
        return SendResult(ok=True, channel="whatsapp", provider="waha")

    async def fake_evolution(**kwargs):
        called.append("evolution")
        return SendResult(ok=True, channel="whatsapp", provider="evolution")

    monkeypatch.setattr(whatsapp_router, "send_whatsapp_waha", fake_waha)
    monkeypatch.setattr(whatsapp_router, "send_whatsapp_evolution", fake_evolution)

    result = await whatsapp_router.send_whatsapp(to="+5521981811077", message="test")

    assert result.provider == "waha"
    assert called == ["waha"]


async def test_whatsapp_router_fails_over_to_evolution_after_http_5xx(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "waha_api_url", "https://waha.test")
    monkeypatch.setattr(settings, "waha_api_key", "test-waha-key")
    monkeypatch.setattr(settings, "evolution_api_url", "https://evolution.test")
    monkeypatch.setattr(settings, "evolution_api_key", "test-evolution-key")
    called = []

    async def failing_waha(**kwargs):
        called.append("waha")
        return SendResult(
            ok=False, channel="whatsapp", provider="waha",
            error="provider retornou HTTP 503", outcome="unknown",
            ambiguous=True, halt_fallback=True,
        )

    async def successful_evolution(**kwargs):
        called.append("evolution")
        return SendResult(ok=True, channel="whatsapp", provider="evolution")

    monkeypatch.setattr(whatsapp_router, "send_whatsapp_waha", failing_waha)
    monkeypatch.setattr(whatsapp_router, "send_whatsapp_evolution", successful_evolution)

    result = await whatsapp_router.send_whatsapp(
        to="+5521981811077", message="test", idempotency_key="same-message-key"
    )

    assert result.ok is True
    assert result.provider == "evolution"
    assert called == ["waha", "evolution"]


async def test_whatsapp_router_does_not_fail_over_on_timeout(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "waha_api_url", "https://waha.test")
    monkeypatch.setattr(settings, "waha_api_key", "test-waha-key")
    monkeypatch.setattr(settings, "evolution_api_url", "https://evolution.test")
    monkeypatch.setattr(settings, "evolution_api_key", "test-evolution-key")
    called = []

    async def timed_out(**kwargs):
        called.append("waha")
        return SendResult(
            ok=False, channel="whatsapp", provider="waha",
            error="timeout ao aguardar resposta do provider", outcome="unknown",
            ambiguous=True, halt_fallback=True,
        )

    async def should_not_run(**kwargs):
        called.append("evolution")
        return SendResult(ok=True, channel="whatsapp", provider="evolution")

    monkeypatch.setattr(whatsapp_router, "send_whatsapp_waha", timed_out)
    monkeypatch.setattr(whatsapp_router, "send_whatsapp_evolution", should_not_run)

    result = await whatsapp_router.send_whatsapp(
        to="+5521981811077", message="test", idempotency_key="same-message-key"
    )

    assert result.ok is False
    assert result.ambiguous is True
    assert called == ["waha"]
