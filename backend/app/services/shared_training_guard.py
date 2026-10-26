"""Mandatory fail-closed gate for datasets that contribute to shared/base training.

The current base-model trainer is synthetic-only. Any future or indirect pipeline
that assembles tenant-derived rows for shared training must call this guard with
every contributing tenant before materializing or fitting the shared dataset.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import NoReturn

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.training_policy import TrainingPolicyDecision, resolve_training_policy


class SharedTrainingBlockedError(ValueError):
    """Raised when any tenant in a shared-training dataset is not authorized."""


async def require_shared_training_authorization(
    session: AsyncSession,
    *,
    contributing_tenant_ids: Iterable[str],
    dataset_eligibility: Mapping[str, bool] | None = None,
    now: datetime | None = None,
) -> dict[str, TrainingPolicyDecision]:
    """Authorize every tenant contributing to shared training, atomically.

    Missing/empty tenant lists and missing eligibility evidence fail closed.
    A single denied tenant blocks the entire operation; callers must not silently
    drop the denied tenant and proceed with a partially rebuilt dataset, because
    that can hide an indirect contribution path or stale dataset membership.
    """
    tenant_ids = list(dict.fromkeys(contributing_tenant_ids))
    if not tenant_ids or any(not tenant_id for tenant_id in tenant_ids):
        raise SharedTrainingBlockedError(
            "Treinamento global bloqueado: lista de instituições contribuintes vazia ou inválida."
        )

    eligibility = dataset_eligibility or {}
    decisions: dict[str, TrainingPolicyDecision] = {}
    denied: list[str] = []
    for tenant_id in tenant_ids:
        decision = await resolve_training_policy(
            session,
            tenant_id=tenant_id,
            purpose="shared_base_training",
            dataset_eligible=eligibility.get(tenant_id, False),
            now=now,
        )
        decisions[tenant_id] = decision
        if not decision.allowed:
            denied.append(f"{tenant_id}: {decision.reason}")

    if denied:
        details = "; ".join(denied)
        raise SharedTrainingBlockedError(
            "Treinamento global bloqueado pela política vigente. "
            f"Instituições negadas: {details}"
        )
    return decisions
