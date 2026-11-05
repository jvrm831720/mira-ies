from app.services.composio.categories import (
    FINANCE_TOOLKITS,
    OMIE_CUSTOM_INTEGRATION,
    annotate_toolkit,
    finance_category,
)


def test_finance_toolkits_receive_category_metadata():
    for slug, metadata in FINANCE_TOOLKITS.items():
        item = annotate_toolkit({"slug": slug, "name": metadata["name"]})
        assert item["mira_category"] == "finance"
        assert item["mira_category_label"] == "Financeiro e gestão financeira"
        assert item["mira_channel"] == metadata["kind"]


def test_unknown_finance_provider_is_not_classified():
    item = annotate_toolkit({"slug": "unknown_finance_platform"})
    assert item["mira_category"] is None
    assert item["mira_category_label"] is None


def test_finance_category_contains_composio_toolkits_and_custom_omie():
    category = finance_category()
    assert category["slug"] == "finance"
    assert category["name"] == "Financeiro e gestão financeira"
    assert {item["slug"] for item in category["composio_toolkits"]} == set(FINANCE_TOOLKITS)
    assert category["custom_integrations"] == [OMIE_CUSTOM_INTEGRATION]
    assert category["custom_integrations"][0]["slug"] == "omie"
    assert category["custom_integrations"][0]["integration_type"] == "custom"
    assert category["custom_integrations"][0]["status"] == "requires_custom_toolkit"
    assert category["native_channels"] == []
