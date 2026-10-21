"""Testes dos conjuntos independentes usados na avaliação dos modelos."""

import numpy as np
import pandas as pd

from app.ml.model import _split_train_calibration_test
from app.ml.tenant_train import _split_tenant_events


def test_base_split_is_disjoint_and_preserves_target_balance():
    X = pd.DataFrame({"feature": np.arange(500)})
    y = pd.Series([0, 1] * 250)

    train, calibration, test = _split_train_calibration_test(X, y, seed=17)

    assert set(train).isdisjoint(calibration)
    assert set(train).isdisjoint(test)
    assert set(calibration).isdisjoint(test)
    assert len(train) + len(calibration) + len(test) == len(X)
    assert all(y.iloc[idx].nunique() == 2 for idx in (train, calibration, test))


def test_tenant_split_keeps_each_student_in_exactly_one_partition():
    df = pd.DataFrame({
        "__group_id": [f"student-{i}" for i in range(100)],
        "label": [i % 2 for i in range(100)],
        "feature": np.arange(100),
    })

    train, calibration, test = _split_tenant_events(df, seed=17)

    train_students = set(train["__group_id"])
    calibration_students = set(calibration["__group_id"])
    test_students = set(test["__group_id"])
    assert train_students.isdisjoint(calibration_students)
    assert train_students.isdisjoint(test_students)
    assert calibration_students.isdisjoint(test_students)
    assert all(part["label"].nunique() == 2 for part in (train, calibration, test))
    assert len(train) + len(calibration) + len(test) == len(df)


def test_tenant_split_rejects_too_few_distinct_students():
    df = pd.DataFrame({
        "__group_id": ["student-1", "student-1", "student-2", "student-2"],
        "label": [0, 1, 0, 1],
    })

    try:
        _split_tenant_events(df)
    except ValueError as exc:
        assert "5 alunos distintos" in str(exc)
    else:
        raise AssertionError("Esperava erro para conjunto sem grupos suficientes")
