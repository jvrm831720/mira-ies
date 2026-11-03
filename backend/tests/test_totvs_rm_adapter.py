"""Testes de contrato do adapter TOTVS RM sem infraestrutura externa."""

import pytest

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
            return "<EduAluno><SAluno><CODCOLIGADA>3</CODCOLIGADA><RA>000045</RA><CPF>12345678900</CPF><EMAIL>pessoa@example.test</EMAIL></SAluno></EduAluno>"

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
    assert asyncio.run(adapter.read_student_record(ra="000045")) == {"CODCOLIGADA": "3", "RA": "000045"}
    assert captured["read"] == {
        "dataserver": "EduAlunoData",
        "primary_key": "3;000045",
    }


def test_rm_student_key_list_uses_getall_filter_and_drops_personal_fields(monkeypatch):
    import asyncio
    import json

    captured = {}

    class FakeRest:
        def __init__(self, **kwargs):
            captured["config"] = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def iter_offset_pages(self, path, **kwargs):
            captured["path"] = path
            captured["pagination"] = kwargs
            yield [
                {"CODCOLIGADA": "003", "RA": "000001", "CPF": "12345678900", "EMAIL": "x@example.test"},
                {"CODCOLIGADA": "003", "RA": "000002", "NOME": "Pessoa Teste", "TELEFONE1": "21999999999"},
            ]

    monkeypatch.setattr("app.services.connectors.totvs_rm.ReadOnlyRestClient", FakeRest)
    config = TotvsRMConfig(
        rest_base_url="https://rm.example.test/rmsrestdataserver/rest",
        soap_endpoint="https://rm.example.test/wsDataServer/MEX",
        username="reader",
        password="secret",
        context=ERPRequestContext(codcoligada="003", codfilial="01"),
    )
    adapter = TotvsRMReadOnlyAdapter(config)

    pages = asyncio.run(
        _collect_pages(adapter.iter_student_keys(page_size=50, max_pages=20, start=100))
    )

    assert captured["path"] == "EduAlunoData"
    assert captured["pagination"]["page_size"] == 50
    assert captured["pagination"]["max_pages"] == 20
    assert captured["pagination"]["start"] == 100
    assert json.loads(captured["pagination"]["query_params"]["filter"]) == [
        "CODCOLIGADA =:CODCOLIGADA",
        "003",
    ]
    assert pages == [
        [{"CODCOLIGADA": "003", "RA": "000001"}, {"CODCOLIGADA": "003", "RA": "000002"}]
    ]


async def _collect_pages(iterator):
    return [page async for page in iterator]



def test_rm_student_key_list_rejects_records_outside_configured_coligada(monkeypatch):
    import asyncio

    class FakeRest:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def iter_offset_pages(self, path, **kwargs):
            yield [{"CODCOLIGADA": "9", "RA": "000001"}]

    monkeypatch.setattr("app.services.connectors.totvs_rm.ReadOnlyRestClient", FakeRest)
    config = TotvsRMConfig(
        rest_base_url="https://rm.example.test/rmsrestdataserver/rest",
        soap_endpoint="https://rm.example.test/wsDataServer/MEX",
        username="reader",
        password="secret",
        context=ERPRequestContext(codcoligada="003"),
    )
    adapter = TotvsRMReadOnlyAdapter(config)

    async def collect():
        return [page async for page in adapter.iter_student_keys()]

    with pytest.raises(ValueError, match="fora da CODCOLIGADA"):
        asyncio.run(collect())



def test_rm_student_readrecord_rejects_response_with_different_ra(monkeypatch):
    import asyncio

    class FakeSoap:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def read_record(self, **kwargs):
            return "<EduAluno><SAluno><CODCOLIGADA>3</CODCOLIGADA><RA>999999</RA></SAluno></EduAluno>"

    monkeypatch.setattr("app.services.connectors.totvs_rm.TotvsReadOnlySoapClient", FakeSoap)
    config = TotvsRMConfig(
        rest_base_url="https://rm.example.test/rest",
        soap_endpoint="https://rm.example.test/soap",
        username="reader",
        password="secret",
        context=ERPRequestContext(codcoligada="3"),
    )
    adapter = TotvsRMReadOnlyAdapter(config)

    with pytest.raises(ValueError, match="RA diferente"):
        asyncio.run(adapter.read_student_record(ra="000045"))
