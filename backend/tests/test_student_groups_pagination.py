"""Testes puros para os cursores HMAC da listagem de grupos."""
from __future__ import annotations

import pytest

from app.student_groups.pagination import (
    ExpiredGroupCursor,
    InvalidGroupCursor,
    create_group_cursor,
    decode_group_cursor,
)


def _cursor(**overrides):
    values = {
        "tenant_id": "tenant-a",
        "group_id": "risk_critical",
        "after_id": "student-2",
        "last_member_id": "student-2",
        "limit": 25,
        "now": 1_800_000_000,
    }
    values.update(overrides)
    return create_group_cursor(**values)


def test_signed_cursor_round_trips_with_query_bindings():
    payload = decode_group_cursor(
        _cursor(),
        tenant_id="tenant-a",
        group_id="risk_critical",
        now=1_800_000_100,
    )
    assert payload["after_id"] == "student-2"
    assert payload["last_member_id"] == "student-2"
    assert payload["limit"] == 25
    assert payload["catalog_version"] == "1.0.0"


@pytest.mark.parametrize(
    ("tenant_id", "group_id"),
    [
        ("tenant-b", "risk_critical"),
        ("tenant-a", "risk_medium"),
    ],
)
def test_cursor_is_bound_to_tenant_and_group(tenant_id, group_id):
    with pytest.raises(InvalidGroupCursor):
        decode_group_cursor(
            _cursor(), tenant_id=tenant_id, group_id=group_id, now=1_800_000_100
        )


def test_tampered_cursor_is_rejected():
    cursor = _cursor()
    tampered = cursor[:-1] + ("A" if cursor[-1] != "A" else "B")
    with pytest.raises(InvalidGroupCursor):
        decode_group_cursor(
            tampered, tenant_id="tenant-a", group_id="risk_critical", now=1_800_000_100
        )


def test_expired_cursor_is_distinguished_from_invalid_cursor():
    with pytest.raises(ExpiredGroupCursor):
        decode_group_cursor(
            _cursor(now=1_800_000_000),
            tenant_id="tenant-a",
            group_id="risk_critical",
            now=1_800_003_601,
        )


def test_catalog_version_change_invalidates_cursor(monkeypatch):
    import app.student_groups.pagination as pagination

    cursor = _cursor()
    monkeypatch.setattr(pagination, "GROUP_CATALOG_VERSION", "2.0.0")
    with pytest.raises(InvalidGroupCursor):
        pagination.decode_group_cursor(
            cursor,
            tenant_id="tenant-a",
            group_id="risk_critical",
            now=1_800_000_100,
        )


def test_malformed_cursor_is_controlled():
    with pytest.raises(InvalidGroupCursor):
        decode_group_cursor("not-a-cursor", tenant_id="tenant-a", group_id="risk_critical")
