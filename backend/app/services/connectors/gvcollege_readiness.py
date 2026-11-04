"""Validação declarativa de prontidão para homologação do GVcollege.

Esta wave não armazena segredos, não descobre views remotamente e não executa
sincronização. O manifesto guarda somente referências opacas e evidências
de validação fornecidas pelo processo institucional.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.services.connectors.gvcollege_api import (
    GvcollegeConfigurationError,
    GvcollegeInstitutionConfig,
)


class GvcollegeConnectionState(StrEnum):
    PENDING_CONFIGURATION = "pending_configuration"
    PENDING_INSTITUTION_VALIDATION = "pending_institution_validation"
    READY_FOR_HOMOLOGATION = "ready_for_homologation"
    HOMOLOGATED = "homologated"


@dataclass(frozen=True)
class GvcollegeConnectionManifest:
    """Manifesto sem credenciais para uma instalação específica.

    secret_reference é um identificador opaco de um cofre/provedor externo.
    Nunca deve conter token, senha, header HTTP ou material secreto.
    """

    config: GvcollegeInstitutionConfig
    auth_provider: str | None = None
    secret_reference: str | None = None
    institution_approved_views: bool = False
    unique_pagination_keys_confirmed: bool = False
    network_egress_restricted: bool = False
    tls_validated: bool = False
    institution_contract_reference: str | None = None
    homologation_evidence_reference: str | None = None
    state: GvcollegeConnectionState = GvcollegeConnectionState.PENDING_CONFIGURATION

    def __post_init__(self) -> None:
        if self.auth_provider is not None and not self.auth_provider.strip():
            raise GvcollegeConfigurationError("auth_provider não pode ser vazio")
        if self.secret_reference is not None:
            value = self.secret_reference.strip()
            if not value or any(char in value for char in "\r\n"):
                raise GvcollegeConfigurationError("Referência de segredo inválida")
            lowered = value.lower()
            if any(marker in lowered for marker in ("bearer ", "password=", "token=")):
                raise GvcollegeConfigurationError(
                    "Informe uma referência opaca, nunca o valor do segredo"
                )
        if self.institution_contract_reference is not None and not self.institution_contract_reference.strip():
            raise GvcollegeConfigurationError("Referência do contrato institucional inválida")
        if self.homologation_evidence_reference is not None and not self.homologation_evidence_reference.strip():
            raise GvcollegeConfigurationError("Referência da evidência de homologação inválida")
        if self.state == GvcollegeConnectionState.HOMOLOGATED and not self.homologation_evidence_reference:
            raise GvcollegeConfigurationError(
                "Estado homologated exige referência de evidência"
            )


@dataclass(frozen=True)
class GvcollegeReadinessCheck:
    key: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class GvcollegeReadinessReport:
    tenant_id: str
    state: GvcollegeConnectionState
    checks: tuple[GvcollegeReadinessCheck, ...]
    ready_for_homologation: bool
    homologated: bool
    sync_permitted: bool = False


def assess_gvcollege_readiness(
    manifest: GvcollegeConnectionManifest,
) -> GvcollegeReadinessReport:
    """Avalia pré-requisitos; nunca promove estado nem libera sincronização."""
    config = manifest.config
    checks = (
        GvcollegeReadinessCheck(
            "endpoint_and_host_allowlist",
            bool(config.base_url and config.allowed_hosts),
            "Endpoint HTTPS e allowlist exata configurados.",
        ),
        GvcollegeReadinessCheck(
            "auth_provider_reference",
            bool(manifest.auth_provider and manifest.secret_reference),
            "Provedor e referência opaca do segredo definidos; segredo não é lido.",
        ),
        GvcollegeReadinessCheck(
            "institution_contract",
            bool(
                manifest.institution_approved_views
                and manifest.institution_contract_reference
                and config.views
            ),
            "Views e campos aprovados e vinculados a uma referência institucional.",
        ),
        GvcollegeReadinessCheck(
            "stable_pagination_keys",
            manifest.unique_pagination_keys_confirmed,
            "A instituição confirmou a unicidade/estabilidade das chaves.",
        ),
        GvcollegeReadinessCheck(
            "network_egress_policy",
            manifest.network_egress_restricted,
            "Política de egress bloqueia redes internas e endpoints de metadata.",
        ),
        GvcollegeReadinessCheck(
            "tls_validation",
            manifest.tls_validated,
            "TLS validado no ambiente institucional autorizado.",
        ),
    )
    ready = all(check.passed for check in checks)
    homologated = (
        ready
        and manifest.state == GvcollegeConnectionState.HOMOLOGATED
        and bool(manifest.homologation_evidence_reference)
    )
    if homologated:
        state = GvcollegeConnectionState.HOMOLOGATED
    elif ready:
        state = GvcollegeConnectionState.READY_FOR_HOMOLOGATION
    elif manifest.auth_provider or manifest.institution_contract_reference:
        state = GvcollegeConnectionState.PENDING_INSTITUTION_VALIDATION
    else:
        state = GvcollegeConnectionState.PENDING_CONFIGURATION

    return GvcollegeReadinessReport(
        tenant_id=config.tenant_id,
        state=state,
        checks=checks,
        ready_for_homologation=ready,
        homologated=homologated,
        # Wave 2 entrega somente configuração/validação. Não há executor.
        sync_permitted=False,
    )
