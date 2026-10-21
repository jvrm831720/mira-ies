"""Casos da definição versionada evadiu/trancou nos 90 dias."""

from datetime import datetime, timedelta, timezone

import pytest

from app.ml.targets import TARGET_DEFINITION_VERSION, derive_target_label


def test_dropout_within_90_days_is_positive():
    scored_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    label, reason = derive_target_label("evadiu", scored_at, scored_at + timedelta(days=90))

    assert (label, reason) == (1, "positive_within_90_days")
    assert TARGET_DEFINITION_VERSION == "evasion_90d_v1"


def test_dropout_after_90_days_is_negative_for_the_90_day_target():
    scored_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    label, reason = derive_target_label("trancou", scored_at, scored_at + timedelta(days=91))

    assert (label, reason) == (0, "negative_after_90_days")


def test_active_student_is_pending_before_horizon_and_negative_after_it():
    scored_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    pending = derive_target_label("ativo", scored_at, scored_at + timedelta(days=89))
    mature = derive_target_label("ativo", scored_at, scored_at + timedelta(days=90))

    assert pending == (None, "pending_90_day_observation")
    assert mature == (0, "negative_observed")


def test_missing_observation_date_stays_unlabeled_and_completion_is_negative():
    scored_at = datetime(2026, 1, 1, tzinfo=timezone.utc)

    assert derive_target_label("ativo", scored_at, None) == (None, "missing_observation_date")
    assert derive_target_label("concluiu", scored_at, scored_at + timedelta(days=10)) == (0, "negative_observed")
    assert derive_target_label("formou", scored_at, scored_at + timedelta(days=20)) == (0, "negative_observed")


def test_transfer_is_excluded_as_a_competing_outcome():
    label, reason = derive_target_label("transferiu", datetime.now(timezone.utc), None)

    assert (label, reason) == (None, "excluded_competing_outcome")


def test_observation_before_score_is_rejected():
    scored_at = datetime(2026, 1, 2, tzinfo=timezone.utc)

    with pytest.raises(ValueError, match="anterior a scored_at"):
        derive_target_label("evadiu", scored_at, scored_at - timedelta(days=1))
