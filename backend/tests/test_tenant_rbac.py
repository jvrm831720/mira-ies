import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.api.tenant_rbac import RolePayload, _validate_permission_ceiling
from app.core.auth import _enforce_custom_request_permission, _permission_for_request, require_roles


def _request(path: str, method: str = "GET") -> Request:
    return Request({
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": method, "scheme": "https", "path": path, "raw_path": path.encode(),
        "query_string": b"", "headers": [], "server": ("test", 443), "client": ("127.0.0.1", 1),
    })


def test_custom_role_rejects_admin_base_role():
    with pytest.raises(ValueError):
        RolePayload(name="Admin customizado", base_role="admin", permissions=[])


def test_custom_role_rejects_unknown_permission():
    with pytest.raises(ValueError):
        RolePayload(name="Analista", base_role="operator", permissions=["system.root"])


def test_custom_role_permission_cannot_exceed_base_role():
    with pytest.raises(HTTPException) as exc:
        _validate_permission_ceiling("viewer", ["campaigns.execute"])
    assert exc.value.status_code == 422


def test_custom_role_permission_accepts_grants_within_base_role():
    _validate_permission_ceiling("coordinator", [
        "access.viewer", "access.operator", "access.coordinator",
        "students.view", "campaigns.approve", "campaigns.execute",
    ])


@pytest.mark.parametrize(
    ("path", "method", "expected"),
    [
        ("/api/v1/students", "GET", "students.view"),
        ("/api/v1/students/123", "PATCH", "students.edit"),
        ("/api/v1/students/123", "DELETE", "students.delete"),
        ("/api/v1/upload", "POST", "data.import"),
        ("/api/v1/agents/retention/campaigns/intelligence/proposals/123/approve", "POST", "campaigns.approve"),
        ("/api/v1/agents/retention/campaigns/intelligence/proposals/123/schedule", "POST", "campaigns.execute"),
        ("/api/v1/org/members", "GET", "members.view"),
        ("/api/v1/org/invites", "POST", "members.manage"),
    ],
)
def test_route_maps_to_explicit_permission(path, method, expected):
    assert _permission_for_request(_request(path, method), "viewer") == expected


def test_unknown_protected_route_falls_back_to_access_level():
    assert _permission_for_request(_request("/api/v1/unknown"), "operator") == "access.operator"


def test_custom_role_always_retains_minimum_application_access():
    payload = RolePayload(name="Consulta", base_role="viewer", permissions=[])
    assert "access.viewer" in payload.permissions


def test_member_role_assignment_requires_permission_management():
    assert _permission_for_request(_request("/api/v1/org/members/123/role", "POST")) == "permissions.manage"
    assert _permission_for_request(_request("/api/v1/org/members/123/permissions", "GET")) == "permissions.manage"


def test_custom_permission_is_enforced_for_authenticated_requests():
    request = _request("/api/v1/students", "GET")
    with pytest.raises(HTTPException) as exc:
        _enforce_custom_request_permission(request, SimpleNamespace(permissions=frozenset({"access.viewer"})))
    assert exc.value.status_code == 403
    _enforce_custom_request_permission(request, SimpleNamespace(permissions=frozenset({"students.view"})))


def test_dashboard_summary_does_not_require_student_detail_permission():
    assert _permission_for_request(_request("/api/v1/risk/summary")) == "dashboard.view"



def test_custom_role_require_roles_checks_explicit_access_tier():
    dependency = require_roles("coordinator")
    allowed = SimpleNamespace(
        permissions=frozenset({"access.viewer", "access.operator", "access.coordinator"}),
        role="coordinator",
    )
    denied = SimpleNamespace(
        permissions=frozenset({"access.viewer"}),
        role="coordinator",
    )
    assert asyncio.run(dependency(allowed)) is allowed
    with pytest.raises(HTTPException) as exc:
        asyncio.run(dependency(denied))
    assert exc.value.status_code == 403
