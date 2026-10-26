"""Fail-closed policy decisions for the MIRA training modalities.

This is a decision helper for the next pipeline-enforcement delivery. It does
not itself start training, approve a dataset, or authorize legal processing.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.data_governance import TenantDataUsePolicy

TrainingPurpose = Literal[
    "shared_base_training",
    "institutional_training",
    "evaluation",
]


@dataclass(frozen=True)
class TrainingPolicyDecision:
    allowed: bool
    tenant_id: str
    purpose: TrainingPurpose
    mode: str
    policy_id: str | None
    reason: str


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


async def resolve_training_policy(
    session: AsyncSession,
    *,
    tenant_id: str,
    purpose: TrainingPurpose,
    dataset_eligible: bool = False,
    now: datetime | None = None,
) -> TrainingPolicyDecision:
    """Resolve the latest effective policy; never revive superseded consent.

    Missing, expired, revoked, or incompletely approved policies never permit
    contribution to shared-base training. Local training remains possible only
    when its dataset has independently passed eligibility checks.
    """
    if purpose not in {
        "shared_base_training",
        "institutional_training",
        "evaluation",
    }:
        raise ValueError(f"Unsupported training purpose: {purpose}")

    instant = _as_utc(now or datetime.now(timezone.utc))
    result = await session.execute(
        select(TenantDataUsePolicy)
        .where(TenantDataUsePolicy.tenant_id == tenant_id)
        .order_by(
            TenantDataUsePolicy.effective_at.desc(),
            TenantDataUsePolicy.created_at.desc(),
        )
    )
    policies = list(result.scalars().all())
    # Select the latest policy that has taken effect, even if it was revoked or
    # expired. Falling back to an older authorization could silently resurrect
    # consent after a later revocation.
    current = next(
        (policy for policy in policies if _as_utc(policy.effective_at) <= instant),
        None,
    )

    def deny(reason: str, mode: str = "unknown", policy_id: str | None = None):
        return TrainingPolicyDecision(
            False, tenant_id, purpose, mode, policy_id, reason
        )

    if current is None:
        if purpose == "shared_base_training":
            return deny("No effective data-use policy; shared training denied by default.")
        return TrainingPolicyDecision(
            bool(dataset_eligible),
            tenant_id,
            purpose,
            "unknown",
            None,
            (
                "No effective policy; locally eligible data may be used only for "
                "institution-scoped work."
                if dataset_eligible
                else "Dataset is not independently eligible."
            ),
        )

    if current.revoked_at is not None:
        return deny("Latest effective data-use policy has been revoked.", current.mode, current.id)
    if current.expires_at is not None and _as_utc(current.expires_at) <= instant:
        return deny("Latest effective data-use policy has expired.", current.mode, current.id)

    approved = bool(
        current.approved_by_admin_id
        and current.evidence_reference
        and current.evidence_reference.strip()
        and current.contract_reference.strip()
        and current.contract_version.strip()
    )
    if not approved:
        return deny("Policy lacks approval or contract evidence.", current.mode, current.id)

    if purpose == "shared_base_training":
        allowed = current.mode == "shared_training" and dataset_eligible
        reason = (
            "Current policy permits shared training and dataset is eligible."
            if allowed
            else (
                "Institution-only policy blocks shared training."
                if current.mode != "shared_training"
                else "Dataset is not eligible for shared training."
            )
        )
        return TrainingPolicyDecision(
            allowed, tenant_id, purpose, current.mode, current.id, reason
        )

    allowed = dataset_eligible
    return TrainingPolicyDecision(
        allowed,
        tenant_id,
        purpose,
        current.mode,
        current.id,
        (
            "Dataset is eligible for institution-scoped use."
            if allowed
            else "Dataset is not independently eligible."
        ),
    )
