from app.services.composio.categories import (
    DATA_ANALYSIS_TOOLKITS,
    annotate_toolkit,
    data_analysis_category,
)


def test_data_analysis_toolkits_receive_category_metadata():
    for slug in ("googlesheets", "excel", "airtable"):
        item = annotate_toolkit({"slug": slug, "name": DATA_ANALYSIS_TOOLKITS[slug]["name"]})
        assert item["mira_category"] == "data_analysis"
        assert item["mira_category_label"] == "Dados, planilhas e análise"
        assert item["mira_channel"] in {"spreadsheet", "structured_database"}


def test_unknown_toolkit_is_not_classified_as_data_analysis():
    item = annotate_toolkit({"slug": "unknown_data_platform"})
    assert item["mira_category"] is None
    assert item["mira_category_label"] is None


def test_data_analysis_category_is_catalog_only():
    category = data_analysis_category()
    assert category["slug"] == "data_analysis"
    assert {item["slug"] for item in category["composio_toolkits"]} == {
        "googlesheets", "excel", "airtable"
    }
    assert category["native_channels"] == []
