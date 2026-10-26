from app.api.control_center_auth import _ROLE_PERMISSIONS
from app.api import mira_admin


def test_mira_admin_read_permission_is_granular():
    # Super Admin uses the explicit wildcard grant; auditor gets only read permissions.
    assert "*" in _ROLE_PERMISSIONS["super_admin"]
    assert "governance:read" in _ROLE_PERMISSIONS["auditor"]
    assert "governance:read" not in _ROLE_PERMISSIONS["operations"]
    assert "governance:read" not in _ROLE_PERMISSIONS["finance"]
    assert "governance:read" not in _ROLE_PERMISSIONS["support"]
    assert "audit:read" in _ROLE_PERMISSIONS["auditor"]


def test_governance_audit_route_is_registered_separately():
    paths = {route.path for route in mira_admin.router.routes}
    assert "/admin/mira-governance/audit" in paths


def test_governance_console_exposes_read_only_inventory_routes():
    paths = {route.path for route in mira_admin.router.routes}
    assert paths == {
        "/admin/mira-governance/modalities",
        "/admin/mira-governance/authorizations",
        "/admin/mira-governance/datasets",
        "/admin/mira-governance/runs",
        "/admin/mira-governance/audit",
    }
