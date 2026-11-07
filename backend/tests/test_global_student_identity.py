"""Wave 1 global portal identity invariants; no live provider calls."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from starlette.requests import Request

from app.api import global_student_auth as auth


def test_cpf_checksum_and_deterministic_hmac_are_required():
    valid = auth.CPFInput(cpf="529.982.247-25")
    assert valid.cpf == "52998224725"
    with pytest.raises(ValidationError):
        auth.CPFInput(cpf="111.111.111-11")
    with pytest.raises(ValidationError):
        auth.CPFInput(cpf="529.982.247-26")
    secret = "example-secret-for-wave-one-test-1234"
    one = auth._digest(secret, "cpf", valid.cpf)
    assert one == auth._digest(secret, "cpf", valid.cpf)
    assert valid.cpf not in one
    assert one != auth._digest(secret, "otp", valid.cpf)
    assert one != auth._digest(secret + "rotated", "cpf", valid.cpf)


def test_registration_normalization_and_otp_input():
    body = auth.RegistrationInput(cpf="52998224725", email=" Aluno@Example.com ",
                                  whatsapp="+55 (21) 99999-9999")
    assert body.email == "aluno@example.com"
    assert body.whatsapp == "5521999999999"
    assert auth.VerificationInput(cpf="52998224725", code="002345").code == "002345"
    with pytest.raises(ValidationError):
        auth.RegistrationInput(cpf="52998224725", email="invalid-email", whatsapp="5521999999999")
    with pytest.raises(ValidationError):
        auth.VerificationInput(cpf="52998224725", code="12345a")


def test_identity_proof_is_not_derived_from_an_email_challenge():
    account = auth.GlobalStudentAccount(
        cpf_digest="a" * 64, email="aluno@example.com", whatsapp="5521999999999"
    )
    assert account.email_verified_at is None
    assert account.identity_verified_at is None
    assert auth._GENERIC["message"] == (
        "Se os dados estiverem corretos, enviaremos um código para o e-mail cadastrado."
    )


def test_feature_is_disabled_without_configuration(monkeypatch):
    monkeypatch.setattr(auth, "get_settings", lambda: SimpleNamespace(
        global_student_portal_enabled=False,
        global_student_identity_secret="example-secret-for-wave-one-test-1234",
        resend_api_key="test", email_from="MIRA <test@example.com>",
    ))
    with pytest.raises(HTTPException) as exc:
        auth._configured()
    assert exc.value.status_code == 503


def test_cross_site_form_cannot_mutate_global_portal():
    request = Request({"type": "http", "method": "POST", "path": "/",
                       "headers": [], "query_string": b"", "scheme": "https"})
    with pytest.raises(HTTPException) as exc:
        auth._action(request)
    assert exc.value.status_code == 403


def test_redis_failure_closes_auth_requests(monkeypatch):
    class Failure:
        async def eval(self, *args):  # noqa: ARG002
            raise ConnectionError("unavailable")

        async def aclose(self):
            return None

    monkeypatch.setattr(auth, "get_settings", lambda: SimpleNamespace(redis_url="redis://localhost:6379/0"))
    monkeypatch.setattr(auth.redis, "from_url", lambda *args, **kwargs: Failure())
    request = Request({"type": "http", "method": "POST", "path": "/",
                       "headers": [], "query_string": b"", "scheme": "https",
                       "client": ("127.0.0.1", 443)})
    with pytest.raises(HTTPException) as exc:
        asyncio.run(auth._throttle(request, "example-secret-for-wave-one-test-1234", "a" * 64))
    assert exc.value.status_code == 503


def test_no_tenant_financial_models_imported_for_global_identity():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1] / "app" / "api" / "global_student_auth.py").read_text()
    assert "from app.models.student import" not in source
    assert "from app.models.dispatch" not in source
    assert "saldo_devedor" not in source
    assert "mira_portal_session" not in source
    assert "identity_verified_at = now" not in source
