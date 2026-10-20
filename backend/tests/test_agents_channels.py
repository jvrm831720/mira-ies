"""Testes unitarios puros: normalizacao de telefone/e-mail e templates."""
from app.agents.base import MessageContext
from app.agents.channels.email import is_valid_email
from app.agents.channels.whatsapp import normalize_phone_br
from app.agents.templates import render_email_body, render_sms, render_whatsapp


def test_normalize_phone_br_accepts_local_11_digits():
    assert normalize_phone_br("11988887777") == "+5511988887777"


def test_normalize_phone_br_accepts_already_with_country_code():
    assert normalize_phone_br("5511988887777") == "+5511988887777"


def test_normalize_phone_br_accepts_formatted_input():
    assert normalize_phone_br("(11) 98888-7777") == "+5511988887777"


def test_normalize_phone_br_rejects_garbage():
    assert normalize_phone_br("abc") is None
    assert normalize_phone_br("") is None
    assert normalize_phone_br(None) is None


def test_is_valid_email():
    assert is_valid_email("aluno@escola.edu.br") is True
    assert is_valid_email("nao-e-email") is False
    assert is_valid_email(None) is False


def _ctx(**overrides) -> MessageContext:
    defaults = dict(
        tenant_id="t1", student_id="s1", matricula="M1", nome="Joao Silva",
        curso="Engenharia", risk_level="critico", risk_score=80.0,
        top_factor_label="Atraso financeiro", recommended_action="Procurar o financeiro",
        telefone="11988887777", email="joao@example.com",
    )
    defaults.update(overrides)
    return MessageContext(**defaults)


def test_render_whatsapp_uses_first_name_and_action():
    msg = render_whatsapp(_ctx())
    assert "Joao" in msg
    assert "Procurar o financeiro" in msg


def test_render_whatsapp_falls_back_when_data_missing():
    msg = render_whatsapp(_ctx(nome="", curso=None, top_factor_label=None, recommended_action=None))
    assert "aluno(a)" in msg
    assert "seu curso" in msg


def test_render_email_body_contains_coordination_signature():
    body = render_email_body(_ctx())
    assert "Coordenacao Academica" in body


def test_render_sms_respects_160_char_limit():
    ctx = _ctx(nome="Nome Bem Comprido Da Silva Pereira", recommended_action="A" * 200)
    msg = render_sms(ctx)
    assert len(msg) <= 160
