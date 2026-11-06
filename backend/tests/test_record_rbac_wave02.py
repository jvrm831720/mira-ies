"""Record Experience: never deliver confidential student fields to non-sensitive roles."""
from types import SimpleNamespace
from uuid import uuid4

from app.api.scoring import _can_read_student_sensitive, _student_record_projection
from app.models.student import Student


def _identity(role, permissions=None, custom_role_id=None):
    return SimpleNamespace(
        tenant_id=str(uuid4()),
        user_id=str(uuid4()) if role is not None else None,
        role=role,
        custom_role_id=custom_role_id,
        permissions=permissions,
    )


def _sample():
    return Student(
        id=str(uuid4()), tenant_id=str(uuid4()), batch_id=str(uuid4()),
        matricula="000123", nome="Aluno Teste", curso="Direito", campus="Centro",
        status_aluno="MATRICULADO", risk_score=78, risk_level="critico",
        saldo_devedor=432.10, dias_atraso_boleto=32,
        status_financeiro="VENCIDO", nota_media=8.5,
        shap_top_factors={"summary": "informação sensível"},
        behavior_properties={"internal": "não expor"},
    )


def test_viewer_projection_omits_confidential_fields_in_payload_not_just_ui():
    student = _sample()
    viewer = _identity("viewer")
    result = _student_record_projection(student, viewer)
    assert result["matricula"] == "000123"
    assert result["nome"] == "Aluno Teste"
    assert result["curso"] == "Direito"
    assert result["tenant_id"] == viewer.tenant_id
    forbidden = {
        "risk_score", "risk_level", "saldo_devedor", "dias_atraso_boleto",
        "status_financeiro", "nota_media", "shap_top_factors",
        "behavior_properties", "communication_preferences",
    }
    assert forbidden.isdisjoint(result)
    assert "432" not in repr(result)


def test_operator_has_no_financial_or_risk_without_explicit_sensitive_grant():
    student = _sample()
    operator = _identity("operator")
    assert not _can_read_student_sensitive(operator)
    assert "risk_score" not in _student_record_projection(student, operator)


def test_custom_role_permissions_override_base_role():
    student = _sample()
    base_admin_custom = _identity("admin", frozenset({"students.view"}), custom_role_id=str(uuid4()))
    assert not _can_read_student_sensitive(base_admin_custom)
    assert "saldo_devedor" not in _student_record_projection(student, base_admin_custom)
    granted = _identity(
        "viewer", frozenset({"students.view", "students.sensitive.view"}),
        custom_role_id=str(uuid4()),
    )
    assert _can_read_student_sensitive(granted)
    result = _student_record_projection(student, granted)
    assert result["risk_score"] == 78
    assert result["saldo_devedor"] == 432.10


def test_coordinator_and_legacy_api_key_preserve_supported_full_contract():
    student = _sample()
    for principal in (_identity("coordinator"), _identity(None)):
        assert _can_read_student_sensitive(principal)
        result = _student_record_projection(student, principal)
        assert result["nota_media"] == 8.5
        assert result["risk_level"] == "critico"


def test_unknown_custom_role_with_no_grants_is_fail_closed():
    auth = _identity("admin", None, custom_role_id=str(uuid4()))
    assert not _can_read_student_sensitive(auth)
