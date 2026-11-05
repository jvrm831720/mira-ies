from types import SimpleNamespace

from app.services.composio.categories import (
    annotate_communication_toolkit,
    communication_category,
    native_communication_channels,
)


def test_communication_toolkits_receive_mira_category_metadata():
    gmail = annotate_communication_toolkit({"slug": "gmail", "name": "Gmail"})
    teams = annotate_communication_toolkit({"slug": "microsoft_teams", "name": "Teams"})
    unrelated = annotate_communication_toolkit({"slug": "github", "name": "GitHub"})

    assert gmail["mira_category"] == "communication"
    assert gmail["mira_channel"] == "email"
    assert teams["mira_category_label"] == "Comunicação"
    assert unrelated["mira_category"] is None
    assert unrelated["mira_category_label"] is None


def test_native_channels_report_configuration_without_exposing_secrets():
    settings = SimpleNamespace(
        waha_api_url="https://waha.example", waha_api_key="waha-secret",
        evolution_api_url=None, evolution_api_key=None,
        resend_api_key="resend-secret", email_from="noreply@example.com",
        twilio_account_sid="AC123", twilio_auth_token="twilio-secret",
        twilio_from="+15550000000",
    )

    channels = native_communication_channels(settings)
    by_slug = {item["slug"]: item for item in channels}

    assert by_slug["whatsapp"]["providers"][0]["configured"] is True
    assert by_slug["whatsapp"]["providers"][1]["configured"] is False
    assert by_slug["email_delivery"]["providers"][0]["configured"] is True
    assert by_slug["sms"]["providers"][0]["configured"] is True
    assert "secret" not in str(channels)


def test_communication_category_separates_composio_and_native_integrations():
    category = communication_category(
        SimpleNamespace(
            waha_api_url=None, waha_api_key=None,
            evolution_api_url=None, evolution_api_key=None,
            resend_api_key=None, email_from=None,
            twilio_account_sid=None, twilio_auth_token=None, twilio_from=None,
        )
    )

    assert category["slug"] == "communication"
    assert {item["slug"] for item in category["composio_toolkits"]} >= {
        "gmail", "outlook", "slack", "microsoft_teams"
    }
    assert {item["slug"] for item in category["native_channels"]} == {
        "whatsapp", "email_delivery", "sms"
    }
