"""Wave 7: domain search grants and view grants must match central RBAC."""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.work_inbox import require_work_access

from app.api.object_views import can_sensitive, can_share, has_permission
from app.core.auth import has_effective_permission


def actor(role, permissions=None, custom_role_id=None):
    return SimpleNamespace(
        role=role, permissions=permissions, custom_role_id=custom_role_id,
        user_id="signed-human", session_id="signed-mfa-session", aal=2,
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

@pytest.mark.asyncio
async def test_work_inbox_denies_custom_student_viewer_and_requires_edit_to_mutate():
    read = require_work_access("access.operator", "students.view")
    write = require_work_access("access.operator", "students.view", "students.edit")
    for identity in (actor("viewer"), actor(
        "coordinator", permissions=frozenset({"students.view"}),
        custom_role_id="readonly",
    )):
        with pytest.raises(HTTPException) as denied:
            await read(identity)
        assert denied.value.status_code == 403

    operator = actor("operator")
    assert await read(operator) is operator
    assert await write(operator) is operator
    read_only_operator = actor(
        "operator", permissions=frozenset({"access.operator", "students.view"}),
        custom_role_id="work-readonly",
    )
    assert await read(read_only_operator) is read_only_operator
    with pytest.raises(HTTPException) as denied:
        await write(read_only_operator)
    assert denied.value.status_code == 403

    operator.aal = 1
    with pytest.raises(HTTPException) as denied:
        await read(operator)
    assert denied.value.status_code == 403
