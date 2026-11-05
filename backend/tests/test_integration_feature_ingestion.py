from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.services.integration_features.contract import (
    FEATURE_KEY_ALLOWLIST,
    FeatureIngestDenied,
    FeatureObservationInput,
    assert_source_may_write_feature,
    normalize_feature_key,
    observation_key_for,
    validate_observation_values,
)


def test_feature_key_allowlist_covers_core_student_fields():
    assert "dias_atraso_boleto" in FEATURE_KEY_ALLOWLIST
    assert "dias_sem_login" in FEATURE_KEY_ALLOWLIST
    assert "nota_media" in FEATURE_KEY_ALLOWLIST


def test_normalize_feature_key_rejects_invalid():
    assert normalize_feature_key("Dias-Sem-Login") == "dias_sem_login"
    with pytest.raises(ValueError):
        normalize_feature_key("1invalid")
    with pytest.raises(ValueError):
        normalize_feature_key("has space")


def test_assert_source_may_write_fails_closed_when_disabled():
    with pytest.raises(FeatureIngestDenied, match="desabilitada"):
        assert_source_may_write_feature(
            source_enabled=False,
            allowed_feature_keys=["dias_sem_login"],
            feature_key="dias_sem_login",
        )


def test_assert_source_may_write_enforces_global_and_source_allowlist():
    with pytest.raises(FeatureIngestDenied, match="allowlist"):
        assert_source_may_write_feature(
            source_enabled=True,
            allowed_feature_keys=None,
            feature_key="unknown_metric",
        )
    with pytest.raises(FeatureIngestDenied, match="não autorizada"):
        assert_source_may_write_feature(
            source_enabled=True,
            allowed_feature_keys=["nota_media"],
            feature_key="dias_sem_login",
        )
    with pytest.raises(FeatureIngestDenied, match="não autorizada"):
        assert_source_may_write_feature(
            source_enabled=True,
            allowed_feature_keys=[],
            feature_key="dias_sem_login",
        )
    assert (
        assert_source_may_write_feature(
            source_enabled=True,
            allowed_feature_keys=["dias_sem_login", "nota_media"],
            feature_key="dias_sem_login",
        )
        == "dias_sem_login"
    )


def test_observation_key_is_stable_per_utc_day_bucket_across_timezones():
    utc_value = datetime(2026, 11, 5, 1, 0, tzinfo=timezone.utc)
    local_value = datetime(2026, 11, 4, 22, 0, tzinfo=timezone(timedelta(hours=-3)))

    first = observation_key_for(
        tenant_id="t1",
        source_kind="composio",
        source_key="google_classroom",
        feature_key="lms_last_activity_days",
        student_id="s1",
        subject_ref=None,
        observed_at=utc_value,
    )
    same_instant = observation_key_for(
        tenant_id="t1",
        source_kind="composio",
        source_key="google_classroom",
        feature_key="lms_last_activity_days",
        student_id="s1",
        subject_ref=None,
        observed_at=local_value,
    )
    assert first == same_instant

    other_day = observation_key_for(
        tenant_id="t1",
        source_kind="composio",
        source_key="google_classroom",
        feature_key="lms_last_activity_days",
        student_id="s1",
        subject_ref=None,
        observed_at=datetime(2026, 11, 6, 1, 0, tzinfo=timezone.utc),
    )
    assert first != other_day
    assert first.startswith("obs_")


def test_observation_key_rejects_naive_datetime():
    with pytest.raises(ValueError, match="timezone explícito"):
        observation_key_for(
            tenant_id="t1",
            source_kind="composio",
            source_key="google_classroom",
            feature_key="lms_last_activity_days",
            student_id="s1",
            subject_ref=None,
            observed_at=datetime(2026, 11, 5, 14, 30),
        )


def test_validate_observation_requires_subject_and_typed_value():
    base = dict(
        tenant_id="t1",
        source_kind="native_connector",
        source_key="sophia",
        feature_key="nota_media",
        value_type="number",
        observed_at=datetime.now(timezone.utc),
        value_number=7.5,
        student_id="s1",
    )
    validate_observation_values(FeatureObservationInput(**base))
    with pytest.raises(ValueError, match="student_id ou subject_ref"):
        validate_observation_values(
            FeatureObservationInput(**{**base, "student_id": None, "subject_ref": None})
        )
    with pytest.raises(ValueError, match="value_number"):
        validate_observation_values(
            FeatureObservationInput(**{**base, "value_number": None})
        )
    with pytest.raises(ValueError, match="Valores incompatíveis"):
        validate_observation_values(
            FeatureObservationInput(**{**base, "value_text": "valor extra"})
        )
    with pytest.raises(ValueError, match="source_key"):
        validate_observation_values(
            FeatureObservationInput(**{**base, "source_key": "../foreign"})
        )
