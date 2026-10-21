"""Servicos de tenant e prontidao do modelo hibrido."""

from __future__ import annotations

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import Tenant, TrainingEvent, ModelArtifact
from app.ml.targets import TARGET_DEFINITION_VERSION

MIN_LABELED_EVENTS = 200
MIN_POSITIVE_LABELS = 20


async def get_or_create_tenant(session: AsyncSession, *, slug: str = "default", name: str | None = None) -> Tenant:
    result = await session.execute(select(Tenant).where(Tenant.slug == slug))
    tenant = result.scalar_one_or_none()
    if tenant:
        return tenant
    tenant = Tenant(slug=slug, name=name or ("IES Demo" if slug == "default" else slug), is_active=True)
    session.add(tenant)
    await session.flush()
    return tenant


async def ensure_base_model_registered(session: AsyncSession) -> ModelArtifact | None:
    result = await session.execute(
        select(ModelArtifact).where(ModelArtifact.scope == "base", ModelArtifact.is_active == True)  # noqa: E712
    )
    existing = result.scalar_one_or_none()
    if existing:
        from app.ml.model import MODEL_PATH
        if existing.storage_path != str(MODEL_PATH):
            existing.storage_path = str(MODEL_PATH)
            await session.flush()
        return existing
    try:
        from app.ml.model import MODEL_PATH, load_meta
        meta = load_meta()
    except Exception:
        MODEL_PATH = None
        meta = {"version": "0.3.1"}
    artifact = ModelArtifact(
        tenant_id=None,
        name="beacon-base",
        version=str(meta.get("version", "0.3.1")),
        scope="base",
        storage_path=str(MODEL_PATH) if MODEL_PATH else None,
        metrics={"auc": meta.get("auc"), "average_precision": meta.get("average_precision"), "brier_score": meta.get("brier_score")},
        feature_columns=meta.get("feature_columns"),
        is_active=True,
    )
    session.add(artifact)
    await session.flush()
    return artifact


async def refresh_tenant_readiness(session: AsyncSession, tenant_id: str) -> Tenant:
    result = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise ValueError("Tenant nao encontrado")
    labeled = await session.execute(
        select(func.count(TrainingEvent.id)).where(
            TrainingEvent.tenant_id == tenant_id,
            TrainingEvent.label.is_not(None),
            TrainingEvent.target_definition == TARGET_DEFINITION_VERSION,
        )
    )
    positives = await session.execute(
        select(func.count(TrainingEvent.id)).where(
            TrainingEvent.tenant_id == tenant_id,
            TrainingEvent.label == 1,
            TrainingEvent.target_definition == TARGET_DEFINITION_VERSION,
        )
    )
    n_labeled = labeled.scalar() or 0
    n_pos = positives.scalar() or 0
    tenant.labeled_events_count = n_labeled
    tenant.positive_labels_count = n_pos
    tenant.tenant_model_ready = n_labeled >= MIN_LABELED_EVENTS and n_pos >= MIN_POSITIVE_LABELS
    await session.flush()
    return tenant


async def get_tenant_learning_stats(session: AsyncSession, tenant_id: str) -> dict:
    tenant = await refresh_tenant_readiness(session, tenant_id)
    unlabeled = await session.execute(
        select(func.count(TrainingEvent.id)).where(TrainingEvent.tenant_id == tenant_id, TrainingEvent.label.is_(None))
    )
    n_unlabeled = unlabeled.scalar() or 0
    legacy = await session.execute(
        select(func.count(TrainingEvent.id)).where(
            TrainingEvent.tenant_id == tenant_id,
            TrainingEvent.label.is_not(None),
            TrainingEvent.target_definition.is_distinct_from(TARGET_DEFINITION_VERSION),
        )
    )
    n_legacy = legacy.scalar() or 0
    active_model = "base"
    if tenant.active_model_id and tenant.tenant_model_ready:
        active_artifact = await session.execute(
            select(ModelArtifact).where(
                ModelArtifact.id == tenant.active_model_id,
                ModelArtifact.tenant_id == tenant_id,
                ModelArtifact.scope == "tenant",
                ModelArtifact.is_active == True,  # noqa: E712
            )
        )
        artifact = active_artifact.scalar_one_or_none()
        if artifact and (artifact.metrics or {}).get("target_definition") == TARGET_DEFINITION_VERSION:
            active_model = "tenant"
    return {
        "tenant_id": tenant.id,
        "slug": tenant.slug,
        "name": tenant.name,
        "labeled_events": tenant.labeled_events_count,
        "positive_labels": tenant.positive_labels_count,
        "unlabeled_events": n_unlabeled,
        "legacy_labeled_events": n_legacy,
        "target_definition": TARGET_DEFINITION_VERSION,
        "tenant_model_ready": tenant.tenant_model_ready,
        "thresholds": {"min_labeled_events": MIN_LABELED_EVENTS, "min_positive_labels": MIN_POSITIVE_LABELS},
        "progress": {
            "labeled_pct": min(100, round(tenant.labeled_events_count / MIN_LABELED_EVENTS * 100, 1)),
            "positive_pct": min(100, round(tenant.positive_labels_count / MIN_POSITIVE_LABELS * 100, 1)),
        },
        "active_model": active_model,
        "message": (
            "Modelo do tenant pronto para treino supervisionado."
            if tenant.tenant_model_ready
            else "Ainda usando modelo base global. Registre observed_at; status ativo só vira negativo após 90 dias."
        ),
    }
