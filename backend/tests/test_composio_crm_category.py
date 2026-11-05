from app.services.composio.categories import annotate_toolkit, crm_category


def test_crm_toolkits_receive_category_metadata():
    expected = {
        "hubspot": "HubSpot",
        "salesforce": "Salesforce",
        "pipedrive": "Pipedrive",
        "dynamics365": "Dynamics 365",
    }

    for slug, name in expected.items():
        annotated = annotate_toolkit({"slug": slug, "name": name})
        assert annotated["mira_category"] == "crm"
        assert annotated["mira_category_label"] == "CRM e relacionamento"
        assert annotated["mira_channel"] == "crm"


def test_crm_category_contains_only_verified_composio_toolkits():
    category = crm_category()
    slugs = {item["slug"] for item in category["composio_toolkits"]}

    assert category["slug"] == "crm"
    assert slugs == {"hubspot", "salesforce", "pipedrive", "dynamics365"}
    assert category["native_channels"] == []


def test_unverified_crm_provider_is_not_misrepresented_as_composio_toolkit():
    annotated = annotate_toolkit({"slug": "rd_station", "name": "RD Station"})

    assert annotated["mira_category"] is None
    assert annotated["mira_category_label"] is None
