"""Testes unitarios puros das regras de canal e anti-spam (sem DB/rede)."""
from datetime import datetime, timedelta, timezone

from app.agents.rules import check_anti_spam, decide_channels, skip_reason_for_no_channel


def test_decide_channels_critico_prioritizes_whatsapp():
    assert decide_channels(risk_level="critico", telefone="11999999999", email="a@a.com") == ["whatsapp", "email", "sms"]


def test_decide_channels_critico_no_phone_falls_back_to_email():
    assert decide_channels(risk_level="critico", telefone=None, email="a@a.com") == ["email"]


def test_decide_channels_critico_missing_contact_returns_empty():
    assert decide_channels(risk_level="critico", telefone=None, email=None) == []


def test_decide_channels_medio_prefers_email_by_default():
    assert decide_channels(risk_level="medio", telefone="11999999999", email="a@a.com") == ["email", "whatsapp"]


def test_decide_channels_medio_prefer_whatsapp_flag_puts_whatsapp_first():
    result = decide_channels(risk_level="medio", telefone="11999999999", email="a@a.com", prefer_whatsapp_medio=True)
    assert result[0] == "whatsapp"


def test_decide_channels_medio_without_email_falls_back_to_whatsapp():
    assert decide_channels(risk_level="medio", telefone="11999999999", email=None) == ["whatsapp"]


def test_decide_channels_baixo_never_fires_even_with_contact_info():
    assert decide_channels(risk_level="baixo", telefone="11999999999", email="a@a.com") == []


def test_skip_reason_for_no_channel():
    assert skip_reason_for_no_channel("baixo") == "risco baixo — sem disparo"
    assert skip_reason_for_no_channel("critico") == "missing_contact"
    assert skip_reason_for_no_channel("medio") == "missing_contact"


def test_anti_spam_blocks_second_contact_within_48h():
    now = datetime.now(timezone.utc)
    last = now - timedelta(hours=10)
    allowed, reason = check_anti_spam(
        channel="whatsapp", now=now, last_contact_at_this_channel=last,
        contacts_last_7_days=1, min_hours_between_contact=48, max_contacts_per_week=3,
    )
    assert allowed is False
    assert "48h" in reason


def test_anti_spam_allows_contact_after_window_expires():
    now = datetime.now(timezone.utc)
    last = now - timedelta(hours=49)
    allowed, reason = check_anti_spam(
        channel="whatsapp", now=now, last_contact_at_this_channel=last,
        contacts_last_7_days=1, min_hours_between_contact=48, max_contacts_per_week=3,
    )
    assert allowed is True
    assert reason is None


def test_anti_spam_blocks_weekly_limit_regardless_of_channel():
    now = datetime.now(timezone.utc)
    allowed, reason = check_anti_spam(
        channel="email", now=now, last_contact_at_this_channel=None,
        contacts_last_7_days=3, min_hours_between_contact=48, max_contacts_per_week=3,
    )
    assert allowed is False
    assert "3 mensagens" in reason


def test_anti_spam_allows_first_contact_with_no_history():
    now = datetime.now(timezone.utc)
    allowed, reason = check_anti_spam(
        channel="sms", now=now, last_contact_at_this_channel=None,
        contacts_last_7_days=0, min_hours_between_contact=48, max_contacts_per_week=3,
    )
    assert allowed is True
    assert reason is None
