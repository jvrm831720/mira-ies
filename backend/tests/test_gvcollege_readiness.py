from __future__ import annotations

import pytest

from app.services.connectors.gvcollege_api import (
    GvcollegeConfigurationError,
    GvcollegeInstitutionConfig,
    GvcollegeViewContract,
)
from app.services.connectors.gvcollege_readiness import (
    GvcollegeConnectionManifest,
    GvcollegeConnectionState,
    assess_gvcollege_readiness,
)


def make_config() -> GvcollegeInstitutionConfig:
    return GvcollegeInstitutionConfig(
        tenant_id="tenant-a",
        base_url="https://erp.instituicao.edu.br",
        allowed_hosts=frozenset({"erp.instituicao.edu.br"}),
        views={
            "pessoa": GvcollegeViewContract(
                view_name="Pessoa",
                source_fields=("codigo", "nome"),
                pagination_key="codigo",
                default_order_by="codigo",
            )
        },
    )


def make_ready_manifest(**overrides) -> GvcollegeConnectionManifest:
    values = {
        "config": make_config(),
        "auth_provider": "institution-secret-provider",
        "secret_reference": "vault://tenant-a/gvcollege/api",
        "institution_approved_views": True,
        "unique_pagination_keys_confirmed": True,
        "network_egress_restricted": True,
        "tls_validated": True,
        "institution_contract_reference": "contract://tenant-a/gvcollege/views-v1",
    }
    values.update(overrides)
    return GvcollegeConnectionManifest(**values)


def test_incomplete_manifest_is_not_ready_and_never_allows_sync():
    report = assess_gvcollege_readiness(
        GvcollegeConnectionManifest(config=make_config())
    )
    assert report.state == GvcollegeConnectionState.PENDING_CONFIGURATION
    assert not report.ready_for_homologation
    assert not report.homologated
    assert not report.sync_permitted


def test_complete_manifest_is_ready_but_not_homologated():
    report = assess_gvcollege_readiness(make_ready_manifest())
    assert report.state == GvcollegeConnectionState.READY_FOR_HOMOLOGATION
    assert report.ready_for_homologation
    assert not report.homologated
    assert not report.sync_permitted


def test_missing_institution_confirmation_blocks_readiness():
    report = assess_gvcollege_readiness(
        make_ready_manifest(unique_pagination_keys_confirmed=False)
    )
    assert not report.ready_for_homologation
    assert not report.sync_permitted
    failed = {check.key for check in report.checks if not check.passed}
    assert "stable_pagination_keys" in failed


def test_homologated_state_requires_evidence_reference():
    with pytest.raises(GvcollegeConfigurationError, match="evidência"):
        make_ready_manifest(state=GvcollegeConnectionState.HOMOLOGATED)


def test_homologation_requires_all_checks_and_evidence():
    report = assess_gvcollege_readiness(
        make_ready_manifest(
            state=GvcollegeConnectionState.HOMOLOGATED,
            homologation_evidence_reference="evidence://tenant-a/run-001",
        )
    )
    assert report.homologated
    # A Wave 2 não contém executor; homologação não ativa sync automaticamente.
    assert not report.sync_permitted


@pytest.mark.parametrize(
    "secret_reference",
    ["Bearer abc123", "password=hunter2", "token=secret", "bad\nvalue"],
)
def test_manifest_rejects_secret_material_in_reference(secret_reference):
    with pytest.raises(GvcollegeConfigurationError):
        make_ready_manifest(secret_reference=secret_reference)
