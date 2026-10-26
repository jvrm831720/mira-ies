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


def _policy_is_current(policy: TenantDataUsePolicy, now: datetime) -> bool:
    effective = policy.effective_at
    if effective.tzinfo is None:
        effective = effective.replace(tzinfo=timezone.utc)
    if effective > now:
        return False

    if policy.expires_at is not None:
        expires = policy.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires <= now:
            return False

    if policy.revoked_at is not None:
        return False

    return True


async def resolve_training_policy(
    session: AsyncSession,
    *,
    tenant_id: str,
    purpose: TrainingPurpose,
    dataset_eligible: bool = False,
    now: datetime | None = None,
) -> TrainingPolicyDecision:
    """Resolve the most recent current policy for a tenant and purpose.

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

    instant = now or datetime.now(timezone.utc)
    result = await session.execute(
        select(TenantDataUsePolicy)
        .where(TenantDataUsePolicy.tenant_id == tenant_id)
        .order_by(
            TenantDataUsePolicy.effective_at.desc(),
            TenantDataUsePolicy.created_at.desc(),
        )
    )
    policies = list(result.scalars().all())
    current = next(
        (policy for policy in policies if _policy_is_current(policy, instant)),
        None,
    )

    if current is None:
        if purpose == "shared_base_training":
            return TrainingPolicyDecision(
                False, tenant_id, purpose, "unknown", None,
                "No current, valid data-use policy; shared training denied by default.",
            )
        return TrainingPolicyDecision(
            bool(dataset_eligible),
            tenant_id,
            purpose,
            "unknown",
            None,
            (
                "No current policy; locally eligible data may be used only for "
                "institution-scoped work."
                if dataset_eligible
                else "Dataset is not independently eligible."
            ),
        )

    approved = bool(
        current.approved_by_admin_id
        and current.evidence_reference
        and current.evidence_reference.strip()
        and current.contract_reference.strip()
        and current.contract_version.strip()
    )
    if not approved:
        return TrainingPolicyDecision(
            False, tenant_id, purpose, current.mode, current.id,
            "Policy lacks approval or contract evidence.",
        )

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
