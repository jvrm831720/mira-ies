"""Fail-closed policy decisions for the MIRA training modalities."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.data_governance import TenantDataUsePolicy
from app.models.institutional_training_authorization import InstitutionalTrainingAuthorization

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


@dataclass(frozen=True)
class InstitutionalAuthorizationDecision:
    allowed: bool
    authorization_id: str | None
    reason: str


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


async def resolve_institutional_training_authorization(
    session: AsyncSession,
    *,
    tenant_id: str,
    now: datetime | None = None,
) -> InstitutionalAuthorizationDecision:
    """Check the latest effective, separately approved local-training record.

    A revoked/expired/newer incomplete record supersedes older authorization.
    The function never treats a sharing policy as local-training authorization.
    """
    instant = _as_utc(now or datetime.now(timezone.utc))
    result = await session.execute(
        select(InstitutionalTrainingAuthorization)
        .where(InstitutionalTrainingAuthorization.tenant_id == tenant_id)
        .order_by(
            InstitutionalTrainingAuthorization.created_at.desc(),
            InstitutionalTrainingAuthorization.effective_at.desc(),
        )
    )
    records = list(result.scalars().all())
    current = next(
        (record for record in records if _as_utc(record.effective_at) <= instant),
        None,
    )
    if current is None:
        return InstitutionalAuthorizationDecision(
            False, None, "No separate institutional-training authorization is recorded."
        )
    if current.revoked_at is not None:
        return InstitutionalAuthorizationDecision(
            False, current.id, "The latest institutional-training authorization was revoked."
        )
    if current.expires_at is not None and _as_utc(current.expires_at) <= instant:
        return InstitutionalAuthorizationDecision(
            False, current.id, "The latest institutional-training authorization has expired."
        )
    if not (
        current.approved_by_admin_id
        and current.evidence_reference
        and current.evidence_reference.strip()
        and current.dataset_eligibility_reference
        and current.dataset_eligibility_reference.strip()
        and current.contract_reference
        and current.contract_reference.strip()
        and current.contract_version
        and current.contract_version.strip()
    ):
        return InstitutionalAuthorizationDecision(
            False, current.id, "Institutional authorization lacks admin approval or contractual evidence."
        )
    return InstitutionalAuthorizationDecision(
        True, current.id, "Current independent institutional-training authorization is valid."
    )


async def resolve_training_policy(
    session: AsyncSession,
    *,
    tenant_id: str,
    purpose: TrainingPurpose,
    dataset_eligible: bool = False,
    institutional_use_authorized: bool = False,
    now: datetime | None = None,
) -> TrainingPolicyDecision:
    """Resolve the latest effective data-use policy; default to deny."""
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
            TenantDataUsePolicy.created_at.desc(),
            TenantDataUsePolicy.effective_at.desc(),
        )
    )
    policies = list(result.scalars().all())
    current = next(
        (policy for policy in policies if _as_utc(policy.effective_at) <= instant),
        None,
    )

    def deny(reason: str, mode: str = "unknown", policy_id: str | None = None):
        return TrainingPolicyDecision(False, tenant_id, purpose, mode, policy_id, reason)

    def local_decision(mode: str, policy_id: str | None, reason_prefix: str = ""):
        allowed = dataset_eligible and institutional_use_authorized
        if allowed:
            reason = "Dataset is eligible and institutional use is independently authorized."
        elif not dataset_eligible:
            reason = "Dataset is not independently eligible for institutional use."
        else:
            reason = "Independent authorization for institutional use is missing."
        if reason_prefix:
            reason = f"{reason_prefix} {reason}"
        return TrainingPolicyDecision(allowed, tenant_id, purpose, mode, policy_id, reason)

    if current is None:
        if purpose == "shared_base_training":
            return deny("No effective data-use policy; shared training denied by default.")
        return local_decision("unknown", None, "No effective sharing policy.")

    if current.revoked_at is not None:
        if purpose == "shared_base_training":
            return deny("Latest effective sharing policy has been revoked.", current.mode, current.id)
        return local_decision(current.mode, current.id, "Sharing policy revoked.")
    if current.expires_at is not None and _as_utc(current.expires_at) <= instant:
        if purpose == "shared_base_training":
            return deny("Latest effective sharing policy has expired.", current.mode, current.id)
        return local_decision(current.mode, current.id, "Sharing policy expired.")

    approved = bool(
        current.approved_by_admin_id
        and current.evidence_reference
        and current.evidence_reference.strip()
        and current.contract_reference.strip()
        and current.contract_version.strip()
    )
    if not approved:
        if purpose == "shared_base_training":
            return deny("Policy lacks approval or contract evidence.", current.mode, current.id)
        return local_decision(current.mode, current.id, "Sharing policy lacks approval or evidence.")

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
        return TrainingPolicyDecision(allowed, tenant_id, purpose, current.mode, current.id, reason)

    return local_decision(current.mode, current.id)
