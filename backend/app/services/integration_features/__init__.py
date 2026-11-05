"""Integration → predictive feature ingestion boundary."""

from app.services.integration_features.contract import (
    FeatureIngestDenied,
    FeatureObservationInput,
    FEATURE_KEY_ALLOWLIST,
    assert_source_may_write_feature,
    normalize_feature_key,
    observation_key_for,
)

__all__ = [
    "FeatureIngestDenied",
    "FeatureObservationInput",
    "FEATURE_KEY_ALLOWLIST",
    "assert_source_may_write_feature",
    "normalize_feature_key",
    "observation_key_for",
]
