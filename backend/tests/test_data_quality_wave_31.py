"""Wave 3.1 regression tests: missing data must never become favorable features."""
import math

import pytest

from app.ml.data_quality import (
    FEATURE_SCHEMA_VERSION,
    InsufficientDataError,
    assess_student_data_quality,
    require_scoreable_student,
)
from app.ml.features import FEATURE_COLUMNS, build_features_from_student, features_to_dataframe


COMPLETE_STUDENT = {
    "dias_atraso_boleto": 0,
    "recorrencia_atrasos": 0,
    "dias_sem_login": 0,
    "presenca_percentual": 100,
    "nota_media": 7,
    "reprovacoes": 0,
    "semestre": 3,
}


def test_complete_data_is_scoreable_and_has_explicit_coverage():
    quality = assess_student_data_quality(COMPLETE_STUDENT)
    assert quality["status"] == "ready"
    assert quality["can_score"] is True
    assert quality["coverage_pct"] == 100
    assert quality["feature_schema_version"] == FEATURE_SCHEMA_VERSION
    assert len(quality["required_fields"]) == 7


@pytest.mark.parametrize("field", list(COMPLETE_STUDENT))
def test_each_missing_source_field_blocks_scoring(field):
    student = {**COMPLETE_STUDENT, field: None}
    quality = assess_student_data_quality(student)
    assert quality["can_score"] is False
    assert quality["status"] == "indeterminate"
    assert quality["coverage_pct"] < 100
    assert field in quality["missing_fields"]
    with pytest.raises(InsufficientDataError):
        build_features_from_student(student)


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("dias_atraso_boleto", -1, "out_of_range"),
        ("dias_sem_login", 3651, "out_of_range"),
        ("presenca_percentual", 101, "out_of_range"),
        ("nota_media", float("nan"), "invalid_number"),
        ("reprovacoes", 1.5, "must_be_integer"),
        ("semestre", True, "boolean_not_numeric"),
        ("recorrencia_atrasos", "desconhecido", "invalid_number"),
    ],
)
def test_invalid_source_values_block_scoring(field, value, reason):
    student = {**COMPLETE_STUDENT, field: value}
    quality = assess_student_data_quality(student)
    assert quality["can_score"] is False
    assert field in quality["invalid_fields"]
    assert next(issue for issue in quality["issues"] if issue["field"] == field)["reason"] == reason


def test_valid_zero_values_are_not_treated_as_missing():
    student = {
        **COMPLETE_STUDENT,
        "dias_atraso_boleto": 0,
        "recorrencia_atrasos": 0,
        "dias_sem_login": 0,
        "presenca_percentual": 0,
        "nota_media": 0,
        "reprovacoes": 0,
        "semestre": 1,
    }
    quality = require_scoreable_student(student)
    features = build_features_from_student(student)
    assert quality["can_score"] is True
    assert features["presenca_percentual"] == 0
    assert features["nota_media"] == 0
    assert features["semestre"] == 1


def test_feature_matrix_rejects_missing_columns_instead_of_filling_zero():
    with pytest.raises(ValueError, match="Feature matrix incompleta"):
        features_to_dataframe([{"dias_atraso_boleto": 0}])


def test_feature_matrix_rejects_nan_and_infinity():
    row = {column: 0.0 for column in FEATURE_COLUMNS}
    row["nota_media"] = math.nan
    with pytest.raises(ValueError, match="ausentes ou não finitos"):
        features_to_dataframe([row])
    row["nota_media"] = math.inf
    with pytest.raises(ValueError, match="ausentes ou não finitos"):
        features_to_dataframe([row])


def test_rules_reject_missing_features_without_favorable_defaults():
    from app.ml.rules import apply_business_rules

    with pytest.raises(ValueError, match="features ausentes"):
        apply_business_rules({"dias_atraso_boleto": 0}, 10.0)


def test_invalid_imported_raw_value_is_not_reported_as_merely_missing():
    student = {
        **COMPLETE_STUDENT,
        "nota_media": 7.0,
        "raw_data": {"nota_media": "nota não publicada"},
    }
    quality = assess_student_data_quality(student)
    assert "nota_media" in quality["invalid_fields"]
    assert "nota_media" not in quality["missing_fields"]
    issue = next(item for item in quality["issues"] if item["field"] == "nota_media")
    assert issue["reason"] == "invalid_number"


def test_blank_latest_import_does_not_reuse_previous_database_value():
    student = {
        **COMPLETE_STUDENT,
        "nota_media": 8.5,
        "raw_data": {"nota_media": ""},
    }
    quality = assess_student_data_quality(student)
    assert quality["can_score"] is False
    assert "nota_media" in quality["missing_fields"]


def test_brazilian_decimal_comma_is_valid_in_raw_import_cells():
    student = {
        **COMPLETE_STUDENT,
        "presenca_percentual": 92.5,
        "nota_media": 8.5,
        "raw_data": {
            "presenca_percentual": "92,5",
            "nota_media": "8,5",
        },
    }
    quality = assess_student_data_quality(student)
    assert quality["can_score"] is True
