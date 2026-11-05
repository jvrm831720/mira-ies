from app.services.composio.categories import annotate_toolkit, productivity_category


def test_productivity_toolkits_receive_category_metadata():
    expected = {
        "asana": ("Asana", "project_management"),
        "trello": ("Trello", "kanban"),
        "clickup": ("ClickUp", "work_management"),
        "notion": ("Notion", "knowledge_and_tasks"),
    }

    for slug, (name, kind) in expected.items():
        annotated = annotate_toolkit({"slug": slug, "name": name})
        assert annotated["mira_category"] == "productivity"
        assert annotated["mira_category_label"] == "Produtividade e tarefas"
        assert annotated["mira_channel"] == kind


def test_productivity_category_contains_only_verified_composio_toolkits():
    category = productivity_category()
    slugs = {item["slug"] for item in category["composio_toolkits"]}

    assert category["slug"] == "productivity"
    assert slugs == {"asana", "trello", "clickup", "notion"}
    assert category["native_channels"] == []


def test_unknown_productivity_provider_is_not_classified():
    annotated = annotate_toolkit({"slug": "unknown_tasks", "name": "Unknown Tasks"})

    assert annotated["mira_category"] is None
    assert annotated["mira_category_label"] is None
