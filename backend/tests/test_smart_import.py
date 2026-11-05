"""Testes do motor de importação inteligente (lógica pura, sem banco)."""

import pandas as pd
import pytest

from app.services.custom_fields import coerce_value, slugify_label
from app.services.smart_import import (
    build_catalog_by_field,
    normalize_header,
    suggest_mapping,
    validate_records,
)


def _catalog(custom=None):
    return build_catalog_by_field(custom or [], canonical_aliases={
        "telefone": ["celular", "whatsapp", "contato"],
        "communication_opt_out": ["opt_out", "nao_contatar", "do_not_contact"],
    })


# ---------------------------------------------------------------------------
# Normalização e slug
# ---------------------------------------------------------------------------

def test_normalize_header_strips_accents_and_symbols():
    assert normalize_header("  Polo de Apoio!! ") == "polo de apoio"
    assert normalize_header("E-mail (Principal)") == "e mail principal"


def test_slugify_label():
    assert slugify_label("Polo de Apoio Presencial") == "polo_de_apoio_presencial"
    assert slugify_label("  Turno/Preferido ") == "turno_preferido"


# ---------------------------------------------------------------------------
# Fuzzy mapping
# ---------------------------------------------------------------------------

def test_alias_exact_match_has_full_confidence():
    mapping, suggestions, unmapped = suggest_mapping(["celular"], _catalog())
    assert mapping["celular"]["field"] == "telefone"
    assert mapping["celular"]["confidence"] == 1.0
    assert not unmapped


def test_fuzzy_match_below_threshold_goes_to_suggestions():
    mapping, suggestions, unmapped = suggest_mapping(["valor devido"], _catalog())
    # "valor devido" ~ "saldo devedor" (0,72): abaixo do auto-aceite, pede confirmação.
    assert "valor devido" not in mapping
    assert suggestions["valor devido"][0]["field"] == "saldo_devedor"
    assert not unmapped


def test_token_containment_auto_accepts_compound_header():
    custom = [{
        "field": "polo_de_apoio", "label": "Polo de Apoio", "aliases": ["polo"],
        "source": "custom", "data_type": "text", "options": [],
        "required": False, "is_pii": False,
    }]
    mapping, _, _ = suggest_mapping(["Polo de Apoio Presencial"], _catalog(custom))
    assert mapping["Polo de Apoio Presencial"]["field"] == "polo_de_apoio"


def test_low_confidence_goes_to_suggestions_not_mapping():
    mapping, suggestions, unmapped = suggest_mapping(["observacoes internas xyz"], _catalog())
    assert "observacoes internas xyz" not in mapping
    assert "observacoes internas xyz" in suggestions or "observacoes internas xyz" in unmapped


def test_tenant_custom_field_participates_in_mapping():
    custom = [{
        "field": "polo_de_apoio", "label": "Polo de Apoio", "aliases": ["polo"],
        "source": "custom", "data_type": "text", "options": [],
        "required": False, "is_pii": False,
    }]
    mapping, _, unmapped = suggest_mapping(["Polo"], _catalog(custom))
    assert mapping["Polo"]["field"] == "polo_de_apoio"
    assert not unmapped


# ---------------------------------------------------------------------------
# Coerção de valores
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("1.234,56", 1234.56), ("1234.56", 1234.56), ("45", 45.0),
])
def test_coerce_number_brazilian_format(raw, expected):
    ok, value, _ = coerce_value(raw, "number")
    assert ok and value == expected


def test_coerce_boolean_pt():
    assert coerce_value("SIM", "boolean")[1] is True
    assert coerce_value("Não", "boolean")[1] is False
    ok, _, error = coerce_value("talvez", "boolean")
    assert not ok and "booleano" in error


def test_coerce_enum_and_date():
    ok, value, _ = coerce_value("vespertino", "enum", ["matutino", "vespertino"])
    assert ok and value == "vespertino"
    ok, value, _ = coerce_value("31/12/2026", "date")
    assert ok and value == "2026-12-31"
    ok, _, error = coerce_value("30/02/2026", "date")
    assert not ok


def test_empty_value_is_not_an_error():
    ok, value, error = coerce_value("", "integer")
    assert ok and value is None and error is None


# ---------------------------------------------------------------------------
# Validação de linhas (dry-run)
# ---------------------------------------------------------------------------

def _df():
    return pd.DataFrame([
        {"Matrícula": "001", "Nome": "Ana", "Valor Devido": "1.000,00", "Polo": "Centro"},
        {"Matrícula": "001", "Nome": "Ana Duplicada", "Valor Devido": "2,00", "Polo": "Sul"},
        {"Matrícula": "", "Nome": "Sem chave", "Valor Devido": "x", "Polo": ""},
    ])


def test_validate_records_flags_duplicates_and_bad_rows():
    catalog = _catalog([{
        "field": "polo", "label": "Polo", "aliases": ["polo"],
        "source": "custom", "data_type": "text", "options": [],
        "required": False, "is_pii": False,
    }])
    index = {e["field"]: e for e in catalog}
    mapping, _, _ = suggest_mapping(list(_df().columns), catalog)
    result = validate_records(_df(), mapping, index)
    assert result["key_stats"]["valid"] == 1
    assert result["key_stats"]["duplicates"] == 1
    messages = [e["message"] for e in result["row_errors"]]
    assert any("duplicada" in m for m in messages)
    assert any("ausente" in m or "Chave" in m for m in messages)


def test_custom_values_are_separated_from_standard():
    custom = [{
        "field": "polo", "label": "Polo", "aliases": ["polo"],
        "source": "custom", "data_type": "text", "options": [],
        "required": False, "is_pii": False,
    }]
    catalog = _catalog(custom)
    index = {e["field"]: e for e in catalog}
    df = pd.DataFrame([{"Matrícula": "001", "Nome": "Ana", "Polo": "Centro"}])
    mapping, _, _ = suggest_mapping(list(df.columns), catalog)
    result = validate_records(df, mapping, index)
    record = result["records"][0]
    assert record["custom"] == {"polo": "Centro"}
    assert record["standard"]["nome"] == "Ana"

def test_decimal_integer_rejected_without_truncation():
    ok, value, error = coerce_value("2.5", "integer")
    assert not ok and value is None and error


def test_non_finite_number_rejected():
    ok, value, error = coerce_value("Infinity", "number")
    assert not ok and value is None and error


def test_overlong_text_rejected_instead_of_truncated():
    ok, value, error = coerce_value("A" * 2001, "text")
    assert not ok and value is None and error


def test_invalid_field_rejects_entire_row():
    catalog = _catalog()
    index = {entry["field"]: entry for entry in catalog}
    df = pd.DataFrame([{"matricula": "001", "nome": "Ana", "semestre": "2.5"}])
    mapping, _, _ = suggest_mapping(list(df.columns), catalog)
    result = validate_records(df, mapping, index)
    assert not result["records"]
    assert result["key_stats"]["invalid"] == 1


def test_fuzzy_mapping_never_accepts_two_headers_for_same_field():
    mapping, suggestions, _ = suggest_mapping(
        ["Nome", "nome", "Matrícula"], _catalog(),
    )
    assert sum(entry["field"] == "nome" for entry in mapping.values()) == 1
    assert ("Nome" in suggestions) or ("nome" in suggestions)
