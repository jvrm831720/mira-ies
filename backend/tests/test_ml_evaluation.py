"""Testes de conjuntos independentes para avaliação temporal e por aluno."""

import numpy as np
import pandas as pd
import pytest

from app.ml.model import _split_train_calibration_test
from app.ml.features import FEATURE_COLUMNS
from app.ml.tenant_train import _blend_with_synthetic, _events_to_dataframe, _split_tenant_events


def test_base_split_is_disjoint_and_preserves_target_balance():
    X = pd.DataFrame({"feature": np.arange(500)})
    y = pd.Series([0, 1] * 250)

    train, calibration, test = _split_train_calibration_test(X, y, seed=17)

    assert set(train).isdisjoint(calibration)
    assert set(train).isdisjoint(test)
    assert set(calibration).isdisjoint(test)
    assert len(train) + len(calibration) + len(test) == len(X)
    assert all(y.iloc[idx].nunique() == 2 for idx in (train, calibration, test))


def _temporal_events(n=100):
    start = pd.Timestamp("2026-01-01T00:00:00Z")
    rows = []
    for i in range(n):
        scored_at = start + pd.Timedelta(days=6 * i)
        label = i % 2
        rows.append({
            "__group_id": f"student-{i}",
            "__scored_at": scored_at,
            "__outcome_at": scored_at + pd.Timedelta(days=30 if label else 100),
            "label": label,
            "feature": i,
        })
    return pd.DataFrame(rows)


def test_tenant_split_is_chronological_and_labels_mature_before_next_period():
    df = _temporal_events()

    train, calibration, test = _split_tenant_events(df, seed=17)

    train_students = set(train["__group_id"])
    calibration_students = set(calibration["__group_id"])
    test_students = set(test["__group_id"])
    assert train_students.isdisjoint(calibration_students)
    assert train_students.isdisjoint(test_students)
    assert calibration_students.isdisjoint(test_students)
    assert all(part["label"].nunique() == 2 for part in (train, calibration, test))
    assert train["__scored_at"].max() < calibration["__scored_at"].min()
    assert calibration["__scored_at"].max() < test["__scored_at"].min()
    assert train["__outcome_at"].max() <= calibration["__scored_at"].min()
    assert calibration["__outcome_at"].max() <= test["__scored_at"].min()
    assert len(train) + len(calibration) + len(test) < len(df)


def test_tenant_split_drops_students_whose_events_cross_temporal_boundaries():
    df = _temporal_events()
    crossing = df.iloc[[0]].copy()
    crossing["__scored_at"] = pd.Timestamp("2027-10-28T00:00:00Z")
    crossing["__outcome_at"] = crossing["__scored_at"] + pd.Timedelta(days=30)
    crossing["label"] = 1
    df = pd.concat([df, crossing], ignore_index=True)

    train, calibration, test = _split_tenant_events(df)

    for part in (train, calibration, test):
        assert "student-0" not in set(part["__group_id"])
    assert len(train) + len(calibration) + len(test) <= len(df) - 2


def test_tenant_split_rejects_too_few_distinct_students():
    start = pd.Timestamp("2026-01-01T00:00:00Z")
    scored = [start + pd.Timedelta(days=i) for i in range(4)]
    df = pd.DataFrame({
        "__group_id": ["student-1", "student-1", "student-2", "student-2"],
        "__scored_at": scored,
        "__outcome_at": [date + pd.Timedelta(days=1) for date in scored],
        "label": [0, 1, 0, 1],
    })

    try:
        _split_tenant_events(df)
    except ValueError as exc:
        assert "5 alunos distintos" in str(exc)
    else:
        raise AssertionError("Esperava erro para conjunto sem grupos suficientes")


def test_tenant_split_rejects_outcome_before_score():
    df = _temporal_events(100)
    df.loc[0, "__outcome_at"] = df.loc[0, "__scored_at"] - pd.Timedelta(days=1)

    with pytest.raises(ValueError, match="outcome_at anterior a scored_at"):
        _split_tenant_events(df)


def test_tenant_split_finds_valid_cut_points_in_irregular_history():
    start = pd.Timestamp("2026-01-01T00:00:00Z")
    labels = [0, 1, 0, 0, 1, 0, 0, 1, 1, 1]
    df = pd.DataFrame({
        "__group_id": [f"student-{i}" for i in range(10)],
        "__scored_at": [start + pd.Timedelta(days=100 * i) for i in range(10)],
        "__outcome_at": [start + pd.Timedelta(days=100 * i + 1) for i in range(10)],
        "label": labels,
    })

    train, calibration, test = _split_tenant_events(df)

    assert all(part["label"].nunique() == 2 for part in (train, calibration, test))
    assert train["__outcome_at"].max() <= calibration["__scored_at"].min()
    assert calibration["__outcome_at"].max() <= test["__scored_at"].min()


def test_synthetic_rows_are_added_only_to_the_real_training_partition():
    df = _temporal_events()
    for feature in FEATURE_COLUMNS:
        df[feature] = 0.0
    train, calibration, test = _split_tenant_events(df)

    blended = _blend_with_synthetic(train, seed=7)
    blended_real_groups = set(blended["__group_id"].dropna())

    assert blended_real_groups == set(train["__group_id"])
    assert blended_real_groups.isdisjoint(set(calibration["__group_id"]))
    assert blended_real_groups.isdisjoint(set(test["__group_id"]))
    assert blended["__group_id"].isna().any()


def test_events_with_different_student_row_ids_share_stable_matricula_group():
    from datetime import datetime, timezone
    from types import SimpleNamespace

    scored_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    events = [
        SimpleNamespace(
            features_snapshot={"dias_atraso_boleto": 0, "recorrencia_atrasos": 0, "dias_sem_login": 0,
                "presenca_percentual": 100, "nota_media": 8, "reprovacoes": 0, "semestre": 3}, label=0, student_id=f"row-{i}",
            matricula=" EVD-01 ", scored_at=scored_at, outcome_at=scored_at,
        )
        for i in range(2)
    ]

    df = _events_to_dataframe(events)

    assert df["__group_id"].tolist() == ["evd-01", "evd-01"]
