"""Regressions for the MIRA transactional OTP email presentation."""

import asyncio

import pytest

from app.core.access_email_template import access_code_email


def test_access_email_contains_same_code_and_expiry_in_both_formats():
    text, html = access_code_email("012345", ttl_minutes=5)
    for rendered in (text, html):
        assert "012345" in rendered
        assert "5 minutos" in rendered
        assert "apenas uma vez" in rendered
        assert "Se você não solicitou este acesso" in rendered
        assert "Equipe MIRA" in rendered
    assert "<table" in html
    assert "#ffffff" in html
    assert "#101112" in html
    assert "#f8f9fa" in html
    assert "#3577f1" in html


@pytest.mark.parametrize("invalid", ["12345", "1234567", "12a456", "１２３４５６", "<b>123"])
def test_access_email_rejects_non_otp_values(invalid):
    with pytest.raises(ValueError):
        access_code_email(invalid)


def test_resend_sends_html_and_plaintext_without_affecting_other_messages(monkeypatch):
    from app.agents.providers import resend_provider as provider

    requests = []

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"id": "email-test-id"}

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, *, json, headers):
            requests.append(json)
            return FakeResponse()

    monkeypatch.setattr(provider.httpx, "AsyncClient", FakeClient)
    settings = provider.get_settings()
    monkeypatch.setattr(settings, "resend_api_key", "test_resend_key")
    monkeypatch.setattr(settings, "email_from", "MIRA <no-reply@example.com>")

    text, html = access_code_email("012345")
    result = asyncio.run(provider.send_email_resend(
        to="recipient@example.com", subject="Seu código de acesso à MIRA",
        body=text, html=html,
    ))
    assert result.ok
    assert requests[-1]["text"] == text
    assert requests[-1]["html"] == html

    result_legacy = asyncio.run(provider.send_email_resend(
        to="recipient@example.com", subject="Aviso", body="Texto simples",
    ))
    assert result_legacy.ok
    assert "html" not in requests[-1]
