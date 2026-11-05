from app.services.composio.categories import (
    MARKETING_TOOLKITS,
    annotate_toolkit,
    marketing_category,
)


def test_marketing_toolkits_receive_category_metadata():
    for slug in ("mailchimp", "brevo", "active_campaign", "customerio"):
        item = annotate_toolkit({"slug": slug, "name": MARKETING_TOOLKITS[slug]["name"]})
        assert item["mira_category"] == "marketing"
        assert item["mira_category_label"] == "Marketing institucional"
        assert item["mira_channel"] in {
            "email_marketing", "multichannel_marketing",
            "marketing_automation", "customer_engagement",
        }


def test_unknown_toolkit_is_not_classified_as_marketing():
    item = annotate_toolkit({"slug": "unknown_marketing"})
    assert item["mira_category"] is None
    assert item["mira_category_label"] is None


def test_marketing_category_is_catalog_only():
    category = marketing_category()
    assert category["slug"] == "marketing"
    assert category["name"] == "Marketing institucional"
    assert {item["slug"] for item in category["composio_toolkits"]} == {
        "mailchimp", "brevo", "active_campaign", "customerio"
    }
    assert category["native_channels"] == []
