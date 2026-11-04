"""Governed training-run boundary (Wave 13.3)."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.eligible_contribution import EligibleContribution
from app.models.training_run import TrainingDatasetSnapshot, TrainingRun
from app.services.contribution_sanitizer import ANONYMIZATION_RULES_VERSION, FEATURE_SCHEMA_VERSION
from app.services.shared_training_guard import require_shared_training_authorization


class TrainingRunBlockedError(ValueError):
    pass


@dataclass(frozen=True)
class TrainingRunRecord:
    run_id: str
    run_key: str
    snapshot_id: str
    dataset_hash: str
    status: str
    scope: str
    tenant_ids: list[str]
    row_count: int


async def create_shared_base_training_run(
    session: AsyncSession, *,
    contributing_tenant_ids: list[str],
    triggered_by_admin_id: str | None = None,
    run_key: str | None = None,
    now: datetime | None = None,
) -> TrainingRunRecord:
    instant = now or datetime.now(timezone.utc)
    tenant_ids = list(dict.fromkeys(contributing_tenant_ids))
    if not tenant_ids:
        raise TrainingRunBlockedError("Lista de instituições contribuintes vazia.")
    decisions = await require_shared_training_authorization(
        session, contributing_tenant_ids=tenant_ids,
        dataset_eligibility={tid: True for tid in tenant_ids}, now=instant,
    )
    authorized = [tid for tid, d in decisions.items() if d.allowed]
    if len(authorized) != len(tenant_ids):
        denied = [tid for tid in tenant_ids if tid not in authorized]
        raise TrainingRunBlockedError(f"Treinamento compartilhado bloqueado. Tenants negados: {', '.join(denied)}")
    result = await session.execute(
        select(EligibleContribution).where(
            EligibleContribution.tenant_id.in_(authorized),
            EligibleContribution.eligibility_status == "eligible",
            EligibleContribution.revoked_at.is_(None),
            EligibleContribution.modality == "shared_training",
        ).order_by(EligibleContribution.tenant_id.asc(), EligibleContribution.created_at.asc())
    )
    contributions = list(result.scalars().all())
    if not contributions:
        raise TrainingRunBlockedError("Nenhuma contribuição elegível e não revogada para os tenants autorizados.")
    present = {c.tenant_id for c in contributions}
    missing = [tid for tid in authorized if tid not in present]
    if missing:
        raise TrainingRunBlockedError(f"Tenants sem contribuição elegível: {', '.join(missing)}")
    contribution_hashes = [c.sanitized_content_hash for c in contributions]
    row_count = sum(c.row_count for c in contributions)
    dataset_hash = hashlib.sha256(json.dumps({
        "contribution_hashes": contribution_hashes, "tenant_ids": sorted(authorized),
        "anonymization_rules_version": ANONYMIZATION_RULES_VERSION,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
    }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    existing_snap = await session.execute(select(TrainingDatasetSnapshot).where(TrainingDatasetSnapshot.dataset_hash == dataset_hash).limit(1))
    snapshot = existing_snap.scalar_one_or_none()
    if snapshot is None:
        snapshot = TrainingDatasetSnapshot(
            id=str(uuid4()), scope="shared_base", dataset_hash=dataset_hash,
            contribution_hashes=contribution_hashes, tenant_ids=authorized, row_count=row_count,
            anonymization_rules_version=ANONYMIZATION_RULES_VERSION,
            feature_schema_version=FEATURE_SCHEMA_VERSION,
            built_by_admin_id=triggered_by_admin_id, built_at=instant,
        )
        session.add(snapshot)
        await session.flush()
    key = (run_key or f"shared-{instant.strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:8]}").strip()
    run = TrainingRun(
        id=str(uuid4()), run_key=key, scope="shared_base", tenant_id=None,
        snapshot_id=snapshot.id, dataset_hash=dataset_hash, status="queued",
        triggered_by_admin_id=triggered_by_admin_id,
    )
    session.add(run)
    await session.flush()
    await session.commit()
    return TrainingRunRecord(
        run_id=run.id, run_key=run.run_key, snapshot_id=snapshot.id, dataset_hash=dataset_hash,
        status=run.status, scope=run.scope, tenant_ids=list(authorized), row_count=snapshot.row_count,
    )


async def mark_run_status(
    session: AsyncSession, *, run_id: str, status: str,
    metrics: dict | None = None, error_message: str | None = None,
    artifact_id: str | None = None, now: datetime | None = None,
) -> TrainingRun:
    if status not in {"queued", "running", "succeeded", "failed", "cancelled"}:
        raise TrainingRunBlockedError(f"Status inválido: {status}")
    instant = now or datetime.now(timezone.utc)
    result = await session.execute(select(TrainingRun).where(TrainingRun.id == run_id).with_for_update())
    run = result.scalar_one_or_none()
    if run is None:
        raise TrainingRunBlockedError("Training run não encontrado.")
    run.status = status
    if status == "running" and run.started_at is None:
        run.started_at = instant
    if status in {"succeeded", "failed", "cancelled"}:
        run.finished_at = instant
    if metrics is not None:
        run.metrics = metrics
    if error_message is not None:
        run.error_message = error_message
    if artifact_id is not None:
        run.artifact_id = artifact_id
    await session.commit()
    return run
