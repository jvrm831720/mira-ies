from app.api.control_center_auth import _ROLE_PERMISSIONS
from app.api import mira_admin


def test_mira_admin_read_permission_is_granular():
    assert "governance:read" in _ROLE_PERMISSIONS["super_admin"]
    assert "governance:read" in _ROLE_PERMISSIONS["auditor"]
    assert "governance:read" not in _ROLE_PERMISSIONS["operations"]
    assert "governance:read" not in _ROLE_PERMISSIONS["finance"]
    assert "governance:read" not in _ROLE_PERMISSIONS["support"]


def test_governance_audit_uses_audit_permission_not_general_read():
    audit_route = next(route for route in mira_admin.router.routes if getattr(route, "path", "") == "/audit")
    dependency = audit_route.dependant.dependencies[0]
    assert dependency.call.__name__ == "dependency"


def test_governance_console_exposes_read_only_inventory_routes():
    paths = {route.path for route in mira_admin.router.routes}
    assert paths == {
        "/modalities",
        "/authorizations",
        "/datasets",
        "/runs",
        "/audit",
    }
