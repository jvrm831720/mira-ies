"""Regression: internal event notes must not cross into student portal responses."""
import pytest

from app.services.student_service_visibility import student_visible_event_note


@pytest.mark.parametrize("actor_type", ["staff", "system", "institution", "", "unknown"])
def test_internal_event_notes_fail_closed(actor_type):
    assert student_visible_event_note(actor_type, "Anotação interna e dados confidenciais") is None


def test_student_authored_note_is_not_redacted():
    assert student_visible_event_note("student", "Pedido registrado") == "Pedido registrado"


def test_absent_note_remains_absent():
    assert student_visible_event_note("staff", None) is None
    assert student_visible_event_note("student", None) is None
