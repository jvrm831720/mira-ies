"""Wave 7: domain search grants and view grants must match central RBAC."""
from types import SimpleNamespace

import pytest

from app.api.object_views import can_sensitive, can_share, has_permission
from app.core.auth import has_effective_permission


def actor(role, permissions=None, custom_role_id=None):
    return SimpleNamespace(
        role=role, permissions=permissions, custom_role_id=custom_role_id,
        user_id="signed-human", session_id="signed-mfa-session",
    )


@pytest.mark.parametrize("role,allowed,denied", [
    ("viewer", ["students.view"], ["audit.view", "campaigns.view", "access.operator"]),
    ("operator", ["students.view", "students.edit", "campaigns.view", "access.operator"],
     ["audit.view", "students.sensitive.view", "permissions.manage"]),
    ("coordinator", ["students.view", "students.sensitive.view", "campaigns.view",
                     "audit.view", "access.operator"],
     ["permissions.manage", "critical.manage"]),
    ("admin", ["audit.view", "students.sensitive.view", "critical.manage"],
     ["nonexistent.permission"]),
])
def test_view_and_search_authorization_matches_route_grants(role, allowed, denied):
    auth = actor(role)
    for name in allowed:
        assert has_effective_permission(auth, name), (role, name)
        assert has_permission(auth, name), (role, name)
    for name in denied:
        assert not has_effective_permission(auth, name), (role, name)
        assert not has_permission(auth, name), (role, name)


def test_coordinator_keeps_view_share_but_cannot_manage_all_permissions():
    coordinator = actor("coordinator")
    assert can_share(coordinator)
    assert not has_permission(coordinator, "permissions.manage")
    assert can_sensitive(coordinator)
    assert not can_share(actor("operator"))


def test_custom_role_explicit_deny_does_not_inherit_base_role():
    custom = actor("coordinator", permissions=frozenset({"students.view"}),
                   custom_role_id="custom")
    assert has_permission(custom, "students.view")
    assert not has_permission(custom, "campaigns.view")
    assert not has_permission(custom, "students.sensitive.view")
    assert not can_share(custom)
    assert not can_sensitive(custom)


def test_custom_share_grant_is_explicit_and_service_key_is_not_human():
    assert can_share(actor("viewer", permissions=frozenset({"permissions.manage"})))
    service = actor(None)
    assert not has_permission(service, "students.view")
    assert not has_permission(service, "access.operator")
    service.user_id = None
    service.session_id = None
    assert not can_share(service)
