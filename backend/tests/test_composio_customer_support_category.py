from app.services.composio.categories import (
    SUPPORT_TOOLKITS,
    annotate_toolkit,
    support_category,
)


def test_support_toolkits_receive_category_metadata():
    for slug in ("zendesk", "zoho_desk"):
        item = annotate_toolkit({"slug": slug, "name": SUPPORT_TOOLKITS[slug]["name"]})
        assert item["mira_category"] == "support"
        assert item["mira_category_label"] == "Atendimento e suporte"
        assert item["mira_channel"] == "helpdesk"


def test_unknown_toolkit_is_not_classified_as_support():
    item = annotate_toolkit({"slug": "unknown_helpdesk"})
    assert item["mira_category"] is None
    assert item["mira_category_label"] is None


def test_support_category_is_catalog_only():
    category = support_category()
    assert category["slug"] == "support"
    assert category["name"] == "Atendimento e suporte"
    assert {item["slug"] for item in category["composio_toolkits"]} == {
        "zendesk", "zoho_desk"
    }
    assert category["native_channels"] == []
