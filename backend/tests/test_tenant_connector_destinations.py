from __future__ import annotations

import pytest

from app.services.connectors.destination_policy import (
    DestinationPolicyError,
    normalize_hostname,
    validate_tenant_destination,
)


def test_exact_host_is_tenant_scoped():
    validate_tenant_destination(
        tenant_id="tenant-a",
        url="https://sis.ies-a.example/api",
        tenant_allowed_hosts={"tenant-a": {"sis.ies-a.example"}, "tenant-b": {"sis.ies-b.example"}},
    )


def test_tenant_a_cannot_use_tenant_b_destination():
    with pytest.raises(DestinationPolicyError, match="não autorizado"):
        validate_tenant_destination(
            tenant_id="tenant-a",
            url="https://sis.ies-b.example/api",
            tenant_allowed_hosts={"tenant-a": {"sis.ies-a.example"}, "tenant-b": {"sis.ies-b.example"}},
        )


def test_missing_tenant_allowlist_fails_closed():
    with pytest.raises(DestinationPolicyError, match="não possui allowlist"):
        validate_tenant_destination(
            tenant_id="tenant-a", url="https://sis.ies-a.example/api",
            tenant_allowed_hosts={"tenant-b": {"sis.ies-a.example"}},
        )


@pytest.mark.parametrize("host", [
    "ies-a.example.attacker.invalid", "localhost", "127.0.0.1",
    "[::1]", "metadata.google.internal", "sis.ies-a.example@attacker.invalid",
])
def test_adversarial_hostnames_are_rejected(host: str):
    with pytest.raises(DestinationPolicyError):
        validate_tenant_destination(
            tenant_id="tenant-a", url=f"https://{host}/api",
            tenant_allowed_hosts={"tenant-a": {"sis.ies-a.example"}},
        )


def test_hostname_normalizes_idna_and_trailing_dot():
    assert normalize_hostname("SIS.IES-A.EXAMPLE.") == "sis.ies-a.example"
