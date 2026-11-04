from app.services.connectors.gvcollege_discovery import (
    SYNTHETIC_GVCOLLEGE_VIEWS,
    discover_synthetic_gvcollege_views,
    get_synthetic_gvcollege_view,
)


def test_discovery_lists_only_local_synthetic_views():
    views = discover_synthetic_gvcollege_views()
    assert {view["view_id"] for view in views} == set(SYNTHETIC_GVCOLLEGE_VIEWS)
    assert all(view["fixture_only"] is True for view in views)
    assert all(view["institution_approved"] is False for view in views)
    assert all(view["remote_discovery_performed"] is False for view in views)


def test_discovery_does_not_invent_vendor_view_names():
    view = get_synthetic_gvcollege_view("synthetic_students_v1")
    assert view.view_id.startswith("synthetic_")
    assert view.pagination_key == "matricula"


def test_unknown_view_is_rejected():
    try:
        get_synthetic_gvcollege_view("GVMVW_ALUNOS")
    except ValueError as exc:
        assert "não registrada" in str(exc)
    else:
        raise AssertionError("View não registrada deveria ser rejeitada")
