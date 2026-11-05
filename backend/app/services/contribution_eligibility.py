"""Assess and record contribution eligibility for shared MIRA Base training.

Modalidade B (institution_only) is hard-blocked. Authorization is re-validated
at assessment time. History is append-only; revocation creates a new row.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.eligible_contribution import EligibleContribution
from app.services.contribution_sanitizer import (
    SanitizationResult,
    sanitize_training_rows,
)
from app.services.training_policy import resolve_training_policy


class ContributionBlockedError(ValueError):
    """Raised when a contribution cannot be recorded as eligible."""


@dataclass(frozen=True)
class EligibilityAssessment:
    contribution_id: str
    tenant_id: str
    status: str
    modality: str
    sanitized_content_hash: str
    row_count: int
    reason: str
    policy_id: str | None


async def assess_contribution(
    session: AsyncSession,
    *,
    tenant_id: str,
    contribution_key: str,
    source_dataset_ref: str,
    source_rows: Sequence[Mapping[str, Any]],
    assessed_by_admin_id: str | None = None,
    approval_reason: str | None = None,
    now: datetime | None = None,
) -> EligibilityAssessment:
    """Sanitize, enforce modality/policy rules, and append an eligibility record.

    Fail-closed paths:
    - institution_only (modalidade B)
    - missing / expired / revoked shared policy
    - failed sanitization
    - empty or unlabeled dataset
    """
    instant = now or datetime.now(timezone.utc)

    # 1) Policy gate — must be shared_training and currently allowed.
    policy_decision = await resolve_training_policy(
        session,
        tenant_id=tenant_id,
        purpose="shared_base_training",
        dataset_eligible=True,  # eligibility is what we are deciding now
        now=instant,
    )

    if policy_decision.mode == "institution_only":
        # Hard technical block for modalidade B — no shared contribution path.
        record = await _append_record(
            session,
            tenant_id=tenant_id,
            contribution_key=contribution_key,
            source_dataset_ref=source_dataset_ref,
            policy_id=policy_decision.policy_id,
            policy_contract_version="n/a",
            modality="institution_only",
            eligibility_status="rejected",
            rejection_reason=(
                "Modalidade B (institution_only): contribution to shared MIRA Base "
                "is permanently blocked."
            ),
            approval_reason=None,
            sanitized_content_hash="blocked-modality-b",
            anonymization_rules_version="n/a",
            feature_schema_version="n/a",
            row_count=0,
            assessed_at=instant,
            assessed_by_admin_id=assessed_by_admin_id,
        )
        await session.commit()
        raise ContributionBlockedError(record.rejection_reason or "Modalidade B blocked.")

    if not policy_decision.allowed or policy_decision.mode != "shared_training":
        reason = policy_decision.reason or "Shared training not authorized."
        record = await _append_record(
            session,
            tenant_id=tenant_id,
            contribution_key=contribution_key,
            source_dataset_ref=source_dataset_ref,
            policy_id=policy_decision.policy_id,
            policy_contract_version="unknown",
            modality=policy_decision.mode or "unknown",
            eligibility_status="rejected",
            rejection_reason=reason,
            approval_reason=None,
            sanitized_content_hash="blocked-policy",
            anonymization_rules_version="n/a",
            feature_schema_version="n/a",
            row_count=0,
            assessed_at=instant,
            assessed_by_admin_id=assessed_by_admin_id,
        )
        await session.commit()
        raise ContributionBlockedError(reason)

    # 2) Sanitization gate
    sanitization: SanitizationResult = sanitize_training_rows(source_rows)
    if sanitization.rejected:
        record = await _append_record(
            session,
            tenant_id=tenant_id,
            contribution_key=contribution_key,
            source_dataset_ref=source_dataset_ref,
            policy_id=policy_decision.policy_id,
            policy_contract_version=_contract_version(policy_decision),
            modality="shared_training",
            eligibility_status="rejected",
            rejection_reason=sanitization.rejection_reason or "Sanitization failed.",
            approval_reason=None,
            sanitized_content_hash="blocked-sanitization",
            anonymization_rules_version=sanitization.anonymization_rules_version,
            feature_schema_version=sanitization.feature_schema_version,
            row_count=0,
            assessed_at=instant,
            assessed_by_admin_id=assessed_by_admin_id,
        )
        await session.commit()
        raise ContributionBlockedError(sanitization.rejection_reason or "Sanitization failed.")

    # A revoked contribution must never become eligible again through an old
    # idempotency key. The audit trail is immutable and keeps the original row.
    revoked = await session.execute(
        select(EligibleContribution.id).where(
            EligibleContribution.tenant_id == tenant_id,
            EligibleContribution.contribution_key == contribution_key,
            EligibleContribution.sanitized_content_hash == sanitization.content_hash,
            EligibleContribution.eligibility_status == "revoked",
        ).limit(1)
    )
    if revoked.scalar_one_or_none() is not None:
        raise ContributionBlockedError("Revoked contribution cannot be reused.")

    # 3) Idempotency — same tenant + key + hash already eligible
    existing = await session.execute(
        select(EligibleContribution).where(
            EligibleContribution.tenant_id == tenant_id,
            EligibleContribution.contribution_key == contribution_key,
            EligibleContribution.sanitized_content_hash == sanitization.content_hash,
            EligibleContribution.eligibility_status == "eligible",
            EligibleContribution.revoked_at.is_(None),
        ).limit(1)
    )
    prior = existing.scalar_one_or_none()
    if prior is not None:
        return EligibilityAssessment(
            contribution_id=prior.id,
            tenant_id=prior.tenant_id,
            status=prior.eligibility_status,
            modality=prior.modality,
            sanitized_content_hash=prior.sanitized_content_hash,
            row_count=prior.row_count,
            reason=prior.approval_reason or "Idempotent replay of existing eligible contribution.",
            policy_id=prior.policy_id,
        )

    # 4) Record as eligible
    reason = (approval_reason or "Sanitized contribution authorized under shared_training policy.").strip()
    record = await _append_record(
        session,
        tenant_id=tenant_id,
        contribution_key=contribution_key,
        source_dataset_ref=source_dataset_ref,
        policy_id=policy_decision.policy_id,
        policy_contract_version=_contract_version(policy_decision),
        modality="shared_training",
        eligibility_status="eligible",
        rejection_reason=None,
        approval_reason=reason,
        sanitized_content_hash=sanitization.content_hash,
        anonymization_rules_version=sanitization.anonymization_rules_version,
        feature_schema_version=sanitization.feature_schema_version,
        row_count=len(sanitization.rows),
        assessed_at=instant,
        assessed_by_admin_id=assessed_by_admin_id,
    )
    await session.commit()
    return EligibilityAssessment(
        contribution_id=record.id,
        tenant_id=record.tenant_id,
        status=record.eligibility_status,
        modality=record.modality,
        sanitized_content_hash=record.sanitized_content_hash,
        row_count=record.row_count,
        reason=record.approval_reason or reason,
        policy_id=record.policy_id,
    )


async def revoke_contribution(
    session: AsyncSession,
    *,
    contribution_id: str,
    reason: str,
    assessed_by_admin_id: str | None = None,
    now: datetime | None = None,
) -> EligibilityAssessment:
    """Append a revoked record superseding the latest eligible contribution."""
    instant = now or datetime.now(timezone.utc)
    result = await session.execute(
        select(EligibleContribution)
        .where(EligibleContribution.id == contribution_id)
        .with_for_update()
    )
    current = result.scalar_one_or_none()
    if current is None:
        raise ContributionBlockedError("Contribution not found.")
    if current.eligibility_status != "eligible" or current.revoked_at is not None:
        raise ContributionBlockedError("Only the current eligible contribution can be revoked.")

    # Latest for tenant+key must still be this one
    latest = await session.execute(
        select(EligibleContribution)
        .where(
            EligibleContribution.tenant_id == current.tenant_id,
            EligibleContribution.contribution_key == current.contribution_key,
        )
        .order_by(EligibleContribution.created_at.desc())
        .limit(1)
    )
    head = latest.scalar_one_or_none()
    if head is None or head.id != current.id:
        raise ContributionBlockedError("Only the most recent contribution record can be revoked.")

    record = await _append_record(
        session,
        tenant_id=current.tenant_id,
        contribution_key=current.contribution_key,
        source_dataset_ref=current.source_dataset_ref,
        policy_id=current.policy_id,
        policy_contract_version=current.policy_contract_version,
        modality=current.modality,
        eligibility_status="revoked",
        rejection_reason=reason.strip(),
        approval_reason=None,
        sanitized_content_hash=current.sanitized_content_hash,
        anonymization_rules_version=current.anonymization_rules_version,
        feature_schema_version=current.feature_schema_version,
        row_count=current.row_count,
        assessed_at=instant,
        assessed_by_admin_id=assessed_by_admin_id,
        revoked_at=instant,
    )
    await session.commit()
    return EligibilityAssessment(
        contribution_id=record.id,
        tenant_id=record.tenant_id,
        status=record.eligibility_status,
        modality=record.modality,
        sanitized_content_hash=record.sanitized_content_hash,
        row_count=record.row_count,
        reason=reason.strip(),
        policy_id=record.policy_id,
    )


async def list_eligible_contribution_hashes(
    session: AsyncSession,
    *,
    tenant_ids: list[str],
) -> dict[str, list[str]]:
    """Return active eligible content hashes per tenant (for shared dataset assembly)."""
    if not tenant_ids:
        return {}
    revoked = aliased(EligibleContribution)
    result = await session.execute(
        select(EligibleContribution).where(
            EligibleContribution.tenant_id.in_(tenant_ids),
            EligibleContribution.eligibility_status == "eligible",
            EligibleContribution.revoked_at.is_(None),
            EligibleContribution.modality == "shared_training",
            # Revocations are immutable new rows, so excluding a revoked_at
            # value on the original eligible row is insufficient.
            ~select(revoked.id).where(
                revoked.tenant_id == EligibleContribution.tenant_id,
                revoked.contribution_key == EligibleContribution.contribution_key,
                revoked.sanitized_content_hash == EligibleContribution.sanitized_content_hash,
                revoked.eligibility_status == "revoked",
            ).exists(),
        )
    )
    out: dict[str, list[str]] = {tid: [] for tid in tenant_ids}
    for row in result.scalars().all():
        out.setdefault(row.tenant_id, []).append(row.sanitized_content_hash)
    return out


def _contract_version(decision) -> str:
    # policy_id is available; contract version is resolved at write time from the policy row
    # when present. Fallback keeps the column non-null.
    return getattr(decision, "contract_version", None) or "policy-bound"


async def _append_record(
    session: AsyncSession,
    *,
    tenant_id: str,
    contribution_key: str,
    source_dataset_ref: str,
    policy_id: str | None,
    policy_contract_version: str,
    modality: str,
    eligibility_status: str,
    rejection_reason: str | None,
    approval_reason: str | None,
    sanitized_content_hash: str,
    anonymization_rules_version: str,
    feature_schema_version: str,
    row_count: int,
    assessed_at: datetime,
    assessed_by_admin_id: str | None,
    revoked_at: datetime | None = None,
) -> EligibleContribution:
    record = EligibleContribution(
        id=str(uuid4()),
        tenant_id=tenant_id,
        contribution_key=contribution_key.strip(),
        source_dataset_ref=source_dataset_ref.strip(),
        policy_id=policy_id,
        policy_contract_version=policy_contract_version,
        modality=modality,
        eligibility_status=eligibility_status,
        rejection_reason=rejection_reason,
        approval_reason=approval_reason,
        sanitized_content_hash=sanitized_content_hash,
        anonymization_rules_version=anonymization_rules_version,
        feature_schema_version=feature_schema_version,
        row_count=row_count,
        assessed_at=assessed_at,
        assessed_by_admin_id=assessed_by_admin_id,
        revoked_at=revoked_at,
    )
    session.add(record)
    await session.flush()
    return record
