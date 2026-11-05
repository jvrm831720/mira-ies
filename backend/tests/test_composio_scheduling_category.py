from app.services.composio.categories import (
    SCHEDULING_TOOLKITS,
    annotate_toolkit,
    scheduling_category,
)


def test_scheduling_toolkits_receive_category_metadata():
    for slug in ("googlecalendar", "calendly", "cal"):
        item = annotate_toolkit({"slug": slug, "name": SCHEDULING_TOOLKITS[slug]["name"]})
        assert item["mira_category"] == "scheduling"
        assert item["mira_category_label"] == "Agenda e agendamento"
        assert item["mira_channel"] in {"calendar", "appointment_booking"}


def test_unknown_toolkit_is_not_classified_as_scheduling():
    item = annotate_toolkit({"slug": "unknown_calendar"})
    assert item["mira_category"] is None
    assert item["mira_category_label"] is None


def test_scheduling_category_is_catalog_only():
    category = scheduling_category()
    assert category["slug"] == "scheduling"
    assert category["name"] == "Agenda e agendamento"
    assert {item["slug"] for item in category["composio_toolkits"]} == {
        "googlecalendar", "calendly", "cal"
    }
    assert category["native_channels"] == []
