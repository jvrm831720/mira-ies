"""Global MIRA Base lifecycle: register candidate, approve, activate, rollback.

Only scope='base' and tenant_id IS NULL artifacts are managed here.
Activation is exclusive: at most one active global base at a time.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.mira_base_lifecycle import MiraBaseLifecycleEvent
from app.models.tenant import ModelArtifact
from app.models.training_run import TrainingRun


class MiraBaseLifecycleError(ValueError):
    """Invalid lifecycle transition for the global base model."""


@dataclass(frozen=True)
class MiraBaseState:
    artifact_id: str
    lifecycle_status: str
    is_active: bool
    version: str
    run_id: str | None
    name: str


async def register_base_candidate(
    session: AsyncSession,
    *,
    name: str,
    version: str,
    run_id: str,
    metrics: dict | None = None,
    feature_columns: list | None = None,
    storage_path: str | None = None,
    actor_admin_id: str | None = None,
    reason: str = "Candidate registered from succeeded shared training run.",
    now: datetime | None = None,
) -> MiraBaseState:
    """Register a global base candidate from a succeeded shared_base training run."""
    instant = now or datetime.now(timezone.utc)
    run = await session.get(TrainingRun, run_id)
    if run is None:
        raise MiraBaseLifecycleError("Training run não encontrado.")
    if run.scope != "shared_base":
        raise MiraBaseLifecycleError("Somente runs shared_base podem gerar candidato MIRA Base.")
    if run.status != "succeeded":
        raise MiraBaseLifecycleError("O run precisa estar com status succeeded.")

    artifact = ModelArtifact(
        id=str(uuid4()),
        tenant_id=None,
        name=name.strip(),
        version=version.strip(),
        scope="base",
        storage_path=storage_path,
        metrics=metrics,
        feature_columns=feature_columns,
        is_active=False,
        run_id=run.id,
        lifecycle_status="candidate",
        trained_at=run.finished_at or instant,
    )
    session.add(artifact)
    await session.flush()

    run.artifact_id = artifact.id
    await _append_event(
        session,
        artifact_id=artifact.id,
        run_id=run.id,
        event_type="register_candidate",
        from_status=None,
        to_status="candidate",
        reason=reason.strip(),
        actor_admin_id=actor_admin_id,
        metadata={"version": version, "dataset_hash": run.dataset_hash},
    )
    await session.commit()
    return MiraBaseState(
        artifact_id=artifact.id,
        lifecycle_status=artifact.lifecycle_status,
        is_active=False,
        version=artifact.version,
        run_id=run.id,
        name=artifact.name,
    )


async def approve_base(
    session: AsyncSession,
    *,
    artifact_id: str,
    actor_admin_id: str | None,
    reason: str,
    now: datetime | None = None,
) -> MiraBaseState:
    artifact = await _require_base_artifact(session, artifact_id)
    if artifact.lifecycle_status != "candidate":
        raise MiraBaseLifecycleError("Somente candidatos podem ser aprovados.")
    instant = now or datetime.now(timezone.utc)
    previous = artifact.lifecycle_status
    artifact.lifecycle_status = "approved"
    artifact.approved_by_user_id = actor_admin_id
    artifact.approved_at = instant
    await _append_event(
        session,
        artifact_id=artifact.id,
        run_id=artifact.run_id,
        event_type="approve",
        from_status=previous,
        to_status="approved",
        reason=reason.strip(),
        actor_admin_id=actor_admin_id,
    )
    await session.commit()
    return _state(artifact)


async def reject_base(
    session: AsyncSession,
    *,
    artifact_id: str,
    actor_admin_id: str | None,
    reason: str,
) -> MiraBaseState:
    artifact = await _require_base_artifact(session, artifact_id)
    if artifact.lifecycle_status not in {"candidate", "approved"}:
        raise MiraBaseLifecycleError("Somente candidate/approved podem ser rejeitados.")
    if artifact.is_active:
        raise MiraBaseLifecycleError("Artefato ativo não pode ser rejeitado; use rollback.")
    previous = artifact.lifecycle_status
    artifact.lifecycle_status = "rejected"
    artifact.is_active = False
    await _append_event(
        session,
        artifact_id=artifact.id,
        run_id=artifact.run_id,
        event_type="reject",
        from_status=previous,
        to_status="rejected",
        reason=reason.strip(),
        actor_admin_id=actor_admin_id,
    )
    await session.commit()
    return _state(artifact)


async def activate_base(
    session: AsyncSession,
    *,
    artifact_id: str,
    actor_admin_id: str | None,
    reason: str,
    now: datetime | None = None,
) -> MiraBaseState:
    """Activate an approved base and retire any previously active base."""
    artifact = await _require_base_artifact(session, artifact_id)
    if artifact.lifecycle_status != "approved":
        raise MiraBaseLifecycleError("Somente artefatos approved podem ser ativados.")
    instant = now or datetime.now(timezone.utc)

    # Retire current active base(s)
    active_result = await session.execute(
        select(ModelArtifact).where(
            ModelArtifact.tenant_id.is_(None),
            ModelArtifact.scope == "base",
            ModelArtifact.is_active.is_(True),
        ).with_for_update()
    )
    for current in active_result.scalars().all():
        if current.id == artifact.id:
            continue
        prev = current.lifecycle_status
        current.is_active = False
        current.lifecycle_status = "retired"
        current.retired_at = instant
        await _append_event(
            session,
            artifact_id=current.id,
            run_id=current.run_id,
            event_type="retire",
            from_status=prev,
            to_status="retired",
            reason=f"Retired by activation of {artifact.id}",
            actor_admin_id=actor_admin_id,
            metadata={"superseded_by": artifact.id},
        )

    previous = artifact.lifecycle_status
    artifact.lifecycle_status = "active"
    artifact.is_active = True
    artifact.activated_at = instant
    artifact.activation_reason = reason.strip()
    await _append_event(
        session,
        artifact_id=artifact.id,
        run_id=artifact.run_id,
        event_type="activate",
        from_status=previous,
        to_status="active",
        reason=reason.strip(),
        actor_admin_id=actor_admin_id,
    )
    await session.commit()
    return _state(artifact)


async def rollback_base(
    session: AsyncSession,
    *,
    target_artifact_id: str,
    actor_admin_id: str | None,
    reason: str,
    now: datetime | None = None,
) -> MiraBaseState:
    """Rollback: activate a previously approved/retired base, retire current active."""
    target = await _require_base_artifact(session, target_artifact_id)
    if target.lifecycle_status not in {"approved", "retired", "active"}:
        raise MiraBaseLifecycleError("Rollback só permite approved/retired/active como destino.")
    instant = now or datetime.now(timezone.utc)

    active_result = await session.execute(
        select(ModelArtifact).where(
            ModelArtifact.tenant_id.is_(None),
            ModelArtifact.scope == "base",
            ModelArtifact.is_active.is_(True),
        ).with_for_update()
    )
    current_active = active_result.scalars().first()
    if current_active and current_active.id == target.id:
        raise MiraBaseLifecycleError("O artefato alvo já está ativo.")

    if current_active:
        prev = current_active.lifecycle_status
        current_active.is_active = False
        current_active.lifecycle_status = "retired"
        current_active.retired_at = instant
        await _append_event(
            session,
            artifact_id=current_active.id,
            run_id=current_active.run_id,
            event_type="retire",
            from_status=prev,
            to_status="retired",
            reason=f"Retired by rollback to {target.id}",
            actor_admin_id=actor_admin_id,
            metadata={"rollback_to": target.id},
        )

    previous = target.lifecycle_status
    target.lifecycle_status = "active"
    target.is_active = True
    target.activated_at = instant
    target.activation_reason = reason.strip()
    target.rollback_of_artifact_id = current_active.id if current_active else None
    target.retired_at = None
    await _append_event(
        session,
        artifact_id=target.id,
        run_id=target.run_id,
        event_type="rollback",
        from_status=previous,
        to_status="active",
        reason=reason.strip(),
        actor_admin_id=actor_admin_id,
        rollback_of_artifact_id=current_active.id if current_active else None,
        metadata={"previous_active": current_active.id if current_active else None},
    )
    await session.commit()
    return _state(target)


async def get_active_base(session: AsyncSession) -> MiraBaseState | None:
    result = await session.execute(
        select(ModelArtifact).where(
            ModelArtifact.tenant_id.is_(None),
            ModelArtifact.scope == "base",
            ModelArtifact.is_active.is_(True),
        ).limit(1)
    )
    artifact = result.scalar_one_or_none()
    return _state(artifact) if artifact else None


async def _require_base_artifact(session: AsyncSession, artifact_id: str) -> ModelArtifact:
    artifact = await session.get(ModelArtifact, artifact_id)
    if artifact is None:
        raise MiraBaseLifecycleError("Artefato não encontrado.")
    if artifact.scope != "base" or artifact.tenant_id is not None:
        raise MiraBaseLifecycleError("Operação restrita à MIRA Base global (scope=base, sem tenant).")
    return artifact


def _state(artifact: ModelArtifact) -> MiraBaseState:
    return MiraBaseState(
        artifact_id=artifact.id,
        lifecycle_status=artifact.lifecycle_status,
        is_active=bool(artifact.is_active),
        version=artifact.version,
        run_id=artifact.run_id,
        name=artifact.name,
    )


async def _append_event(
    session: AsyncSession,
    *,
    artifact_id: str,
    run_id: str | None,
    event_type: str,
    from_status: str | None,
    to_status: str,
    reason: str,
    actor_admin_id: str | None,
    rollback_of_artifact_id: str | None = None,
    metadata: dict | None = None,
) -> None:
    session.add(
        MiraBaseLifecycleEvent(
            id=str(uuid4()),
            artifact_id=artifact_id,
            run_id=run_id,
            event_type=event_type,
            from_status=from_status,
            to_status=to_status,
            reason=reason,
            actor_admin_id=actor_admin_id,
            rollback_of_artifact_id=rollback_of_artifact_id,
            metadata_redacted=metadata,
        )
    )
