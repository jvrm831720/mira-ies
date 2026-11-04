"""Policy-gated assembly of sanitized rows for shared training.

No tenant-derived row is materialized until every contributing tenant passes
the shared-training policy AND has at least one eligible (non-revoked)
contribution. Returns only SanitizedTrainingRow — never raw TrainingEvent.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.contribution_eligibility import list_eligible_contribution_hashes
from app.services.shared_training_guard import require_shared_training_authorization


@dataclass(frozen=True)
class SanitizedTrainingRow:
    """Shareable training unit. No matricula, student_id, or tenant-local IDs."""
    contribution_id_hash: str
    tenant_contribution_hash: str
    # Features are already sanitized at eligibility time; this structure is the
    # contract for future training pipelines (Wave 13.3).


async def build_shared_training_dataset(
    session: AsyncSession,
    *,
    contributing_tenant_ids: list[str],
    dataset_eligibility: dict[str, bool] | None,
) -> list[SanitizedTrainingRow]:
    """Return sanitized contribution references for authorized tenants only.

    Replaces the previous helper that returned full TrainingEvent objects.
    Modalidade B tenants never appear: the policy guard rejects them first,
    and eligible_contributions only stores shared_training rows as eligible.
    """
    decisions = await require_shared_training_authorization(
        session,
        contributing_tenant_ids=contributing_tenant_ids,
        dataset_eligibility=dataset_eligibility,
    )
    authorized_tenant_ids = [tid for tid, d in decisions.items() if d.allowed]
    if not authorized_tenant_ids:
        raise ValueError("Dataset global sem instituições autorizadas.")

    hashes_by_tenant = await list_eligible_contribution_hashes(
        session, tenant_ids=authorized_tenant_ids
    )

    rows: list[SanitizedTrainingRow] = []
    for tenant_id in authorized_tenant_ids:
        for content_hash in hashes_by_tenant.get(tenant_id, []):
            rows.append(
                SanitizedTrainingRow(
                    contribution_id_hash=content_hash,
                    tenant_contribution_hash=f"{tenant_id}:{content_hash}",
                )
            )

    if not rows:
        raise ValueError(
            "Nenhuma contribuição elegível e sanitizada encontrada para os tenants autorizados."
        )
    return rows


# Backward-compatible name that must not be used for production shared training.
# Kept only to fail loudly if residual callers still import the old contract.
async def build_shared_training_events(*args, **kwargs):
    raise RuntimeError(
        "build_shared_training_events was retired in Wave 13.2. "
        "Use build_shared_training_dataset, which returns only sanitized rows."
    )
