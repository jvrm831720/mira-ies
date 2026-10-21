"""Testes unitarios puros dos transformers de conectores (sem DB)."""
import pytest

from app.services.connectors.erp import (
    JacadConnector, SponteConnector, SophiaConnector, GvcollegeConnector, WpensarConnector,
)
from app.services.connectors.lms import MoodleConnector, CanvasConnector
from app.services.connectors.generic import GenericConnector
from app.services.connectors.registry import get_connector, list_connectors


def test_jacad_transform_maps_fields():
    records = JacadConnector().transform([
        {"codigoAluno": "123", "nomeAluno": "Ana Silva", "periodo": "3", "diasAtraso": "10", "frequencia": "85.5"},
    ])
    assert len(records) == 1
    r = records[0]
    assert r["matricula"] == "123"
    assert r["nome"] == "Ana Silva"
    assert r["semestre"] == 3
    assert r["dias_atraso_boleto"] == 10
    assert r["presenca_percentual"] == 85.5
    assert r["source_id"] == "jacad"


def test_jacad_transform_skips_rows_without_matricula_or_nome():
    records = JacadConnector().transform([{"nomeAluno": "Sem matricula"}, {"codigoAluno": "1"}])
    assert records == []


def test_sponte_computes_presenca_from_faltas_when_missing():
    records = SponteConnector().transform([
        {"AlunoID": "A1", "Nome": "Bruno", "Faltas": "10", "TotalAulas": "40"},
    ])
    assert records[0]["presenca_percentual"] == pytest.approx(75.0)


def test_sophia_transform_basic():
    records = SophiaConnector().transform([
        {"cod_aluno": "S1", "nome": "Carla", "media": "8.2", "frequencia": "90"},
    ])
    assert records[0]["matricula"] == "S1"
    assert records[0]["nota_media"] == 8.2


def test_gvcollege_transform_nested_structure():
    records = GvcollegeConnector().transform([
        {
            "aluno": {"alunoCodigo": "G1", "alunoNome": "Diego"},
            "financeiro": {"diasAtraso": "20"},
            "academico": {"frequencia": "60", "media": "5.5"},
        },
    ])
    r = records[0]
    assert r["matricula"] == "G1"
    assert r["nome"] == "Diego"
    assert r["dias_atraso_boleto"] == 20
    assert r["presenca_percentual"] == 60
    assert r["nota_media"] == 5.5


def test_wpensar_transform_english_fields():
    records = WpensarConnector().transform([
        {"student_id": "W1", "name": "Elisa", "days_overdue": "5", "attendance": "95"},
    ])
    r = records[0]
    assert r["matricula"] == "W1"
    assert r["dias_atraso_boleto"] == 5
    assert r["presenca_percentual"] == 95


def test_moodle_transform_computes_days_since_login():
    import time
    thirty_days_ago = time.time() - 30 * 86400
    records = MoodleConnector().transform([
        {"id": "M1", "fullname": "Fabio Souza", "lastaccess": thirty_days_ago, "completion_pct": 70},
    ])
    r = records[0]
    assert r["matricula"] == "M1"
    assert r["dias_sem_login"] in (29, 30, 31)


def test_canvas_transform_normalizes_grade_over_10():
    records = CanvasConnector().transform([
        {"sis_user_id": "C1", "name": "Gui Lima", "current_score": 85},
    ])
    assert records[0]["nota_media"] == pytest.approx(8.5)


def test_generic_transform_accepts_canonical_and_aliases():
    records = GenericConnector().transform({"students": [
        {"ra": "GEN1", "name": "Helena", "attendance": "99"},
    ]})
    r = records[0]
    assert r["matricula"] == "GEN1"
    assert r["nome"] == "Helena"
    assert r["presenca_percentual"] == 99.0


def test_generic_transform_returns_empty_for_none_payload():
    assert GenericConnector().transform(None) == []


def test_erp_connectors_map_native_phone_and_email_fields():
    cases = [
        (JacadConnector(), {"codigoAluno": "J1", "nomeAluno": "Ana", "telefoneAluno": "1199", "emailAluno": "ana@x.com"}),
        (SponteConnector(), {"AlunoID": "S1", "Nome": "Bia", "Celular": "1188", "Email": "bia@x.com"}),
        (SophiaConnector(), {"cod_aluno": "H1", "nome": "Caio", "fone": "1177", "email_aluno": "caio@x.com"}),
        (GvcollegeConnector(), {"aluno": {"alunoCodigo": "G1", "alunoNome": "Dani", "celular": "1166", "email": "dani@x.com"}}),
        (WpensarConnector(), {"student_id": "W1", "name": "Eva", "mobile_phone": "1155", "email_address": "eva@x.com"}),
    ]
    for connector, payload in cases:
        record = connector.transform([payload])[0]
        assert record["telefone"]
        assert record["email"].endswith("@x.com")


def test_lms_connectors_map_native_phone_and_email_fields():
    moodle = MoodleConnector().transform([{"id": "M1", "fullname": "Fabi", "phone1": "1144", "email": "fabi@x.com"}])[0]
    canvas = CanvasConnector().transform([{"sis_user_id": "C1", "name": "Gui", "user": {"phone": "1133", "email": "gui@x.com"}}])[0]
    assert moodle["telefone"] == "1144"
    assert moodle["email"] == "fabi@x.com"
    assert canvas["telefone"] == "1133"
    assert canvas["email"] == "gui@x.com"


def test_registry_unknown_connector_raises_keyerror():
    with pytest.raises(KeyError):
        get_connector("does-not-exist")


def test_registry_list_connectors_is_deduplicated_and_sorted():
    items = list_connectors()
    ids = [c.id for c in items]
    assert len(ids) == len(set(ids))
    keys = [(c.category, c.name) for c in items]
    assert keys == sorted(keys)
    assert "generic" in ids and "jacad" in ids and "moodle" in ids
