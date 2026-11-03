"""Testes de contrato do adapter TOTVS RM sem infraestrutura externa."""

from app.services.connectors.totvs_rm import TotvsRMConfig, TotvsRMReadOnlyAdapter
from app.services.connectors.transport import ERPRequestContext


def test_rm_config_requires_coligada_and_hides_password_from_repr():
    try:
        TotvsRMConfig(
            rest_base_url="https://rm.example.test/rest",
            soap_endpoint="https://rm.example.test/soap",
            username="reader",
            password="top-secret",
            context=ERPRequestContext(),
        )
        assert False, "Expected missing CODCOLIGADA to be rejected"
    except ValueError as exc:
        assert "CODCOLIGADA" in str(exc)

    config = TotvsRMConfig(
        rest_base_url="https://rm.example.test/rest",
        soap_endpoint="https://rm.example.test/soap",
        username="reader",
        password="top-secret",
        context=ERPRequestContext(codcoligada="3"),
    )
    assert "top-secret" not in repr(config)


def test_rm_student_lookup_uses_composite_key_and_preserves_ra_leading_zeroes(monkeypatch):
    captured = {}

    class FakeSoap:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def read_record(self, **kwargs):
            captured["read"] = kwargs
            return "<Aluno />"

    monkeypatch.setattr("app.services.connectors.totvs_rm.TotvsReadOnlySoapClient", FakeSoap)
    config = TotvsRMConfig(
        rest_base_url="https://rm.example.test/rest",
        soap_endpoint="https://rm.example.test/soap",
        username="reader",
        password="secret",
        context=ERPRequestContext(codcoligada="3"),
    )
    adapter = TotvsRMReadOnlyAdapter(config)

    import asyncio
    assert asyncio.run(adapter.read_student_record(ra="000045")) == "<Aluno />"
    assert captured["read"] == {
        "dataserver": "EduAlunoData",
        "primary_key": "3;000045",
    }
