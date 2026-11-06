from __future__ import annotations

import pytest

from app.services.connectors.destination_policy import (
    DestinationPolicyError,
    validate_tenant_destination,
)


POLICY = {
    "tenant-a": {"lms.example.edu.br", "erp.example.com"},
    "tenant-b": {"erp.example.com"},
}


def test_accepts_exact_tenant_host_and_normalizes_case_and_trailing_dot():
    assert validate_tenant_destination(
        tenant_id="tenant-a",
        url="https://LMS.Example.edu.br./api/v1",
        tenant_allowed_hosts=POLICY,
    ) == "https://lms.example.edu.br/api/v1"


def test_rejects_host_allowed_for_another_tenant():
    with pytest.raises(DestinationPolicyError, match="não autorizado"):
        validate_tenant_destination(
            tenant_id="tenant-b",
            url="https://lms.example.edu.br",
            tenant_allowed_hosts=POLICY,
        )


@pytest.mark.parametrize(
    "url",
    [
        "http://lms.example.edu.br",
        "https://user:pass@lms.example.edu.br",
        "https://lms.example.edu.br.evil.test",
        "https://127.0.0.1",
        "https://[::1]",
        "https://localhost",
        "https://metadata.google.internal",
        "https://lms.example.edu.br:8443",
        "https://lms.example.edu.br?next=https://evil.test",
        "https://lms.example.edu.br#fragment",
        "https://lms.example.edu.br/../admin",
        "https://lms.example.edu.br/%2e%2e/admin",
        "https://lms.example.edu.br/%252e%252e/admin",
        "https://bad_host.example.com",
        "https://-bad.example.com",
        "https://lms.example.edu.br\\\\@evil.test",
    ],
)
def test_rejects_unsafe_or_unapproved_destinations(url: str):
    with pytest.raises(DestinationPolicyError):
        validate_tenant_destination(
            tenant_id="tenant-a",
            url=url,
            tenant_allowed_hosts=POLICY,
        )


def test_http_requires_explicit_opt_in_and_port_allowance():
    assert validate_tenant_destination(
        tenant_id="tenant-a",
        url="http://erp.example.com",
        tenant_allowed_hosts=POLICY,
        allowed_ports={80, 443},
        allow_http=True,
    ) == "http://erp.example.com"


def test_missing_tenant_allowlist_fails_closed():
    with pytest.raises(DestinationPolicyError, match="allowlist"):
        validate_tenant_destination(
            tenant_id="tenant-missing",
            url="https://lms.example.edu.br",
            tenant_allowed_hosts=POLICY,
        )
