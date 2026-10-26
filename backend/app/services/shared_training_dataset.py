"""Policy-gated assembly of tenant-derived rows for shared training.

No tenant-derived row is queried/materialized until every contributing tenant passes
the current shared-training policy. The current global baseline is synthetic-only;
this is the mandatory entry point for any future shared dataset pipeline.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import TrainingEvent
from app.services.shared_training_guard import require_shared_training_authorization
from app.ml.targets import TARGET_DEFINITION_VERSION


async def build_shared_training_events(
    session: AsyncSession,
    *,
    contributing_tenant_ids: list[str],
    dataset_eligibility: dict[str, bool] | None,
) -> list[TrainingEvent]:
    """Return eligible labeled events, failing closed before querying tenant rows."""
    decisions = await require_shared_training_authorization(
        session,
        contributing_tenant_ids=contributing_tenant_ids,
        dataset_eligibility=dataset_eligibility,
    )
    authorized_tenant_ids = [tenant_id for tenant_id, decision in decisions.items() if decision.allowed]
    if not authorized_tenant_ids:
        # Guard already rejects an empty set; keep a second boundary at the data layer.
        raise ValueError("Dataset global sem instituições autorizadas.")
    result = await session.execute(
        select(TrainingEvent).where(
            TrainingEvent.tenant_id.in_(authorized_tenant_ids),
            TrainingEvent.label.is_not(None),
            TrainingEvent.target_definition == TARGET_DEFINITION_VERSION,
        ).order_by(TrainingEvent.created_at.asc(), TrainingEvent.id.asc())
    )
    return list(result.scalars().all())
