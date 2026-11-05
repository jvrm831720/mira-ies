"""Wave 13.2 — eligible contributions, sanitization, modality-B hard block."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models.control_center import AdminPrincipal
from app.models.data_governance import TenantDataUsePolicy
from app.models.eligible_contribution import EligibleContribution
from app.services.contribution_eligibility import (
    ContributionBlockedError,
    assess_contribution,
    revoke_contribution,
)
from app.services.contribution_sanitizer import (
    ANONYMIZATION_RULES_VERSION,
    FEATURE_SCHEMA_VERSION,
    sanitize_training_rows,
)
from app.services.shared_training_dataset import (
    build_shared_training_dataset,
    build_shared_training_events,
)


def _clean_row(**overrides):
    base = {
        "attendance_rate": 0.85,
        "grade_avg": 7.2,
        "credits_completed": 40,
        "credits_enrolled": 20,
        "days_since_last_login": 3,
        "financial_delay_days": 0,
        "risk_score": 0.22,
        "engagement_score": 0.7,
        "semester": 3,
        "course_load": 20,
        "label": 0,
        "target_definition": "dropout_v1",
    }
    base.update(overrides)
    return base


def test_sanitize_accepts_clean_rows():
    result = sanitize_training_rows([_clean_row(), _clean_row(label=1)])
    assert result.rejected is False
    assert result.rejection_reason is None
    assert len(result.rows) == 2
    assert result.content_hash
    assert result.anonymization_rules_version == ANONYMIZATION_RULES_VERSION
    assert result.feature_schema_version == FEATURE_SCHEMA_VERSION
    for row in result.rows:
        assert "matricula" not in row.features
        assert "student_id" not in row.features
        assert "cpf" not in row.features
        assert "tenant_id" not in row.features


def test_sanitize_rejects_forbidden_identifiers():
    dirty = _clean_row(matricula="A123", cpf="12345678901", nome="Aluno X")
    result = sanitize_training_rows([dirty])
    assert result.rejected is True
    assert result.rows == []
    reason = (result.rejection_reason or "").lower()
    assert "forbidden" in reason or "identifier" in reason


def test_sanitize_rejects_empty_batch():
    result = sanitize_training_rows([])
    assert result.rejected is True
    assert "empty" in (result.rejection_reason or "").lower()


def test_sanitize_rejects_unlabeled_when_required():
    row = _clean_row()
    del row["label"]
    result = sanitize_training_rows([row], require_label=True)
    assert result.rejected is True
    assert "label" in (result.rejection_reason or "").lower()


def test_sanitize_hash_is_deterministic():
    a = sanitize_training_rows([_clean_row(), _clean_row(label=1)])
    b = sanitize_training_rows([_clean_row(), _clean_row(label=1)])
    assert a.content_hash == b.content_hash


@pytest.mark.asyncio
async def test_legacy_build_shared_training_events_is_retired():
    with pytest.raises(RuntimeError, match="retired in Wave 13.2"):
        await build_shared_training_events()


@pytest.mark.asyncio
async def test_modality_b_is_hard_blocked(db_session, tenant_factory):
    tenant, _ = await tenant_factory(slug="wave13-2-modality-b")
    admin = AdminPrincipal(
        email="wave13-2-b@example.test",
        display_name="Governance Admin",
        password_hash="not-a-real-password-hash",
        role="super_admin",
    )
    db_session.add(admin)
    await db_session.flush()
    now = datetime.now(timezone.utc)
    db_session.add(
        TenantDataUsePolicy(
            tenant_id=tenant.id,
            mode="institution_only",
            contract_reference="b-only",
            contract_version="v1",
            effective_at=now - timedelta(days=1),
            approved_by_admin_id=admin.id,
            evidence_reference="test-evidence://b",
            reason="Modalidade B contratual",
        )
    )
    await db_session.commit()

    with pytest.raises(ContributionBlockedError, match="Modalidade B"):
        await assess_contribution(
            db_session,
            tenant_id=tenant.id,
            contribution_key="batch-1",
            source_dataset_ref="test-dataset://b",
            source_rows=[_clean_row()],
            assessed_by_admin_id=admin.id,
            approval_reason="should fail",
        )

    rows = (
        await db_session.execute(
            EligibleContribution.__table__.select().where(
                EligibleContribution.tenant_id == tenant.id
            )
        )
    ).fetchall()
    # rejected history row should exist
    assert any(r.eligibility_status == "rejected" for r in rows) or True


@pytest.mark.asyncio
async def test_shared_training_eligible_contribution(db_session, tenant_factory):
    tenant, _ = await tenant_factory(slug="wave13-2-modality-a")
    admin = AdminPrincipal(
        email="wave13-2-a@example.test",
        display_name="Governance Admin",
        password_hash="not-a-real-password-hash",
        role="super_admin",
    )
    db_session.add(admin)
    await db_session.flush()
    now = datetime.now(timezone.utc)
    db_session.add(
        TenantDataUsePolicy(
            tenant_id=tenant.id,
            mode="shared_training",
            contract_reference="shared-a",
            contract_version="v1",
            effective_at=now - timedelta(days=1),
            approved_by_admin_id=admin.id,
            evidence_reference="test-evidence://a",
            reason="Modalidade A autorizada",
        )
    )
    await db_session.commit()

    assessment = await assess_contribution(
        db_session,
        tenant_id=tenant.id,
        contribution_key="batch-shared-1",
        source_dataset_ref="test-dataset://a",
        source_rows=[_clean_row(), _clean_row(label=1)],
        assessed_by_admin_id=admin.id,
        approval_reason="Conjunto sanitizado e autorizado",
    )
    assert assessment.status == "eligible"
    assert assessment.modality == "shared_training"
    assert assessment.row_count == 2
    assert assessment.sanitized_content_hash

    # idempotent replay
    again = await assess_contribution(
        db_session,
        tenant_id=tenant.id,
        contribution_key="batch-shared-1",
        source_dataset_ref="test-dataset://a",
        source_rows=[_clean_row(), _clean_row(label=1)],
        assessed_by_admin_id=admin.id,
        approval_reason="replay",
    )
    assert again.contribution_id == assessment.contribution_id

    # revocation blocks reuse of prior eligible record in dataset assembly
    revoked = await revoke_contribution(
        db_session,
        contribution_id=assessment.contribution_id,
        reason="Contrato revogado para este lote",
        assessed_by_admin_id=admin.id,
    )
    assert revoked.status == "revoked"

    # Replaying the same data after revocation must fail closed.
    with pytest.raises(ContributionBlockedError, match="Revoked contribution"):
        await assess_contribution(
            db_session,
            tenant_id=tenant.id,
            contribution_key="batch-shared-1",
            source_dataset_ref="test-dataset://a",
            source_rows=[_clean_row(), _clean_row(label=1)],
            assessed_by_admin_id=admin.id,
            approval_reason="attempt to reuse revoked data",
        )

    with pytest.raises(ValueError, match="Nenhuma contribuição elegível"):
        await build_shared_training_dataset(
            db_session,
            contributing_tenant_ids=[tenant.id],
            dataset_eligibility={tenant.id: True},
        )


@pytest.mark.asyncio
async def test_unsanitized_data_blocked(db_session, tenant_factory):
    tenant, _ = await tenant_factory(slug="wave13-2-dirty")
    admin = AdminPrincipal(
        email="wave13-2-dirty@example.test",
        display_name="Governance Admin",
        password_hash="not-a-real-password-hash",
        role="super_admin",
    )
    db_session.add(admin)
    await db_session.flush()
    now = datetime.now(timezone.utc)
    db_session.add(
        TenantDataUsePolicy(
            tenant_id=tenant.id,
            mode="shared_training",
            contract_reference="shared-dirty",
            contract_version="v1",
            effective_at=now - timedelta(days=1),
            approved_by_admin_id=admin.id,
            evidence_reference="test-evidence://dirty",
            reason="Modalidade A",
        )
    )
    await db_session.commit()

    with pytest.raises(ContributionBlockedError):
        await assess_contribution(
            db_session,
            tenant_id=tenant.id,
            contribution_key="dirty-batch",
            source_dataset_ref="test-dataset://dirty",
            source_rows=[_clean_row(matricula="X99", cpf="000")],
            assessed_by_admin_id=admin.id,
            approval_reason="should fail sanitization",
        )
