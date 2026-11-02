import numpy as np
import pandas as pd
import pytest

from app.ml import explain


class FakeExplainer:
    def __init__(self, values):
        self.values = values

    def shap_values(self, frame):
        return self.values


def test_shap_explainer_is_bound_to_exact_scoring_estimator(monkeypatch):
    estimator = object()
    other_estimator = object()
    captured = {}

    def fake_get_explainer(model):
        captured["model"] = model
        return FakeExplainer(np.arange(len(explain.FEATURE_COLUMNS), dtype=float).reshape(1, -1))

    monkeypatch.setattr(explain, "get_explainer", fake_get_explainer)
    features = {column: 1.0 for column in explain.FEATURE_COLUMNS}

    result = explain.explain_instance(
        features,
        top_k=2,
        model=estimator,
        model_scope="tenant",
        model_version="tenant-v9",
    )

    assert captured["model"] is estimator
    assert captured["model"] is not other_estimator
    assert len(result) == 2
    assert all(item["model_scope"] == "tenant" for item in result)
    assert all(item["model_version"] == "tenant-v9" for item in result)
    assert result[0]["impact_pct"] > result[1]["impact_pct"]


def test_shap_does_not_silently_replace_invalid_contribution_shape(monkeypatch):
    monkeypatch.setattr(
        explain,
        "get_explainer",
        lambda model: FakeExplainer(np.zeros((1, 2))),
    )
    features = {column: 1.0 for column in explain.FEATURE_COLUMNS}

    with pytest.raises(ValueError, match="contribuições"):
        explain.explain_instance(
            features,
            model=object(),
            model_scope="base",
            model_version="0.3.2",
        )


def test_rule_adjustments_include_observed_evidence_and_delta():
    from app.ml.rules import apply_business_rules

    features = {
        "dias_atraso_boleto": 35,
        "recorrencia_atrasos": 3,
        "dias_sem_login": 22,
        "presenca_percentual": 45,
        "nota_media": 3.5,
        "reprovacoes": 2,
        "semestre": 1,
    }
    result = apply_business_rules(features, model_score=30.0)

    assert result["rule_boost"] > 0
    assert result["rule_adjustments"]
    delay = next(item for item in result["rule_adjustments"] if item["flag"] == "atraso_financeiro_critico")
    assert delay["source"] == "business_rule"
    assert delay["delta_points"] == 15
    assert delay["evidence"]["observed"] == 35
    assert delay["evidence"]["threshold"] == 30
    assert delay["recommendation"]


def test_confidence_is_explicitly_heuristic_not_probability():
    from app.ml.rules import apply_business_rules

    features = {
        "dias_atraso_boleto": 0,
        "recorrencia_atrasos": 0,
        "dias_sem_login": 0,
        "presenca_percentual": 100,
        "nota_media": 9,
        "reprovacoes": 0,
        "semestre": 4,
    }
    result = apply_business_rules(features, model_score=10)

    assert result["confidence_basis"] == "heuristic_model_rule_band_agreement"
