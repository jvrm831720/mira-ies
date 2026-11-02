from app.services.connectors.base import extract_field_provenance
from app.services.connectors.generic import GenericConnector
from app.services.connectors.erp import JacadConnector
from app.services.connectors.lms import MoodleConnector


def test_extracts_explicit_field_observation_and_source_update_separately():
    result = extract_field_provenance(
        {
            "field_observations": {
                "dias_sem_login": {
                    "observed_at": "2026-11-01T12:00:00Z",
                    "source_updated_at": "2026-11-01T12:05:00Z",
                    "source_field": "lastaccess",
                }
            }
        },
        "moodle",
    )

    assert result["dias_sem_login"]["observed_at"] == "2026-11-01T12:00:00Z"
    assert result["dias_sem_login"]["source_updated_at"] == "2026-11-01T12:05:00Z"
    assert result["dias_sem_login"]["source_field"] == "lastaccess"
    assert result["dias_sem_login"]["source_system"] == "moodle"


def test_source_updated_at_alone_does_not_become_observed_at():
    result = extract_field_provenance(
        {
            "field_observations": {
                "nota_media": {"source_updated_at": "2026-11-01T12:00:00Z"}
            }
        },
        "jacad",
    )

    assert "observed_at" not in result["nota_media"]
    assert result["nota_media"]["source_updated_at"] == "2026-11-01T12:00:00Z"


def test_generic_connector_preserves_field_observations():
    records = GenericConnector().transform({
        "students": [{
            "matricula": "A1",
            "nome": "Aluno",
            "dias_sem_login": 3,
            "field_observations": {
                "dias_sem_login": {"observed_at": "2026-11-01T12:00:00Z"}
            },
        }]
    })

    assert records[0]["__mira_provenance"]["dias_sem_login"]["observed_at"] == "2026-11-01T12:00:00Z"


def test_erp_connector_preserves_field_observations():
    records = JacadConnector().transform([{
        "codigoAluno": "A1",
        "nomeAluno": "Aluno",
        "diasSemAcesso": 3,
        "field_observations": {
            "dias_sem_login": {"observed_at": "2026-11-01T12:00:00Z"}
        },
    }])

    assert records[0]["__mira_provenance"]["dias_sem_login"]["observed_at"] == "2026-11-01T12:00:00Z"


def test_lms_connector_does_not_infer_observation_from_event_or_login_timestamp():
    records = MoodleConnector().transform([{
        "idnumber": "A1",
        "fullname": "Aluno",
        "lastaccess": 1793534400,
    }])

    assert records[0]["__mira_provenance"] == {}


def test_legacy_updated_at_is_not_used_as_field_observation():
    result = extract_field_provenance(
        {
            "updated_at": "2026-11-01T12:00:00Z",
            "created_at": "2026-10-01T12:00:00Z",
        },
        "generic",
    )

    assert result == {}
