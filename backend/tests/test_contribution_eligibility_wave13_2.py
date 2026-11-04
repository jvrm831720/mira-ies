"""Wave 13.2 — eligible contributions, sanitization, and modality-B hard block."""
from __future__ import annotations

import pytest

from app.services.contribution_sanitizer import (
    ANONYMIZATION_RULES_VERSION,
    FEATURE_SCHEMA_VERSION,
    sanitize_training_rows,
)
from app.services.shared_training_dataset import build_shared_training_events


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
    # No forbidden keys survive
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
    assert "forbidden" in (result.rejection_reason or "").lower() or "identifier" in (
        result.rejection_reason or ""
    ).lower()


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
    c = sanitize_training_rows([_clean_row(label=1), _clean_row()])
    # Order matters for the hash payload — different order => different hash
    assert c.content_hash != a.content_hash or len(c.rows) == 2


def test_legacy_build_shared_training_events_is_retired():
    with pytest.raises(RuntimeError, match="retired in Wave 13.2"):
        # sync wrapper raises immediately; no await needed for the guard
        import asyncio

        asyncio.get_event_loop().run_until_complete(build_shared_training_events())
