"""Templates PT-BR das mensagens de retencao, por canal e nivel de risco.

Tom institucional de coordenacao academica. Nunca inventa dados sensiveis —
usa fallbacks genericos quando nome/curso/fator estiverem ausentes.
"""

from __future__ import annotations

from app.agents.base import MessageContext

_FALLBACK_NOME = "aluno(a)"
_FALLBACK_CURSO = "seu curso"
_FALLBACK_ACTION = "procure a coordenacao para conversarmos"

SMS_MAX_LEN = 160


def _primeiro_nome(ctx: MessageContext) -> str:
    return ctx.nome.strip().split(" ")[0] if ctx.nome and ctx.nome.strip() else _FALLBACK_NOME


def _curso(ctx: MessageContext) -> str:
    return ctx.curso or _FALLBACK_CURSO


def _acao(ctx: MessageContext) -> str:
    return ctx.recommended_action or _FALLBACK_ACTION


def _sinal_risco(ctx: MessageContext) -> str:
    if ctx.top_factor_label:
        return f"Notamos sinais de dificuldade (ex.: {ctx.top_factor_label})."
    return "Notamos alguns sinais de dificuldade recentes."


def render_whatsapp(ctx: MessageContext) -> str:
    nome, curso, acao, sinal = _primeiro_nome(ctx), _curso(ctx), _acao(ctx), _sinal_risco(ctx)
    if ctx.risk_level == "critico":
        return (
            f"Ola, {nome}. Aqui e a coordenacao do curso de {curso}. {sinal} "
            f"Queremos te ajudar — {acao}. Responda esta mensagem ou procure a secretaria. "
            f"Estamos com voce."
        )
    return f"Ola, {nome}! Aqui e a coordenacao de {curso}. {sinal} Que tal {acao}? Estamos aqui se precisar."


def render_email_subject(ctx: MessageContext) -> str:
    curso = _curso(ctx)
    if ctx.risk_level == "critico":
        return f"{curso} — queremos te ajudar a continuar"
    return f"{curso} — como podemos te apoiar"


def render_email_body(ctx: MessageContext) -> str:
    nome, curso, acao, sinal = _primeiro_nome(ctx), _curso(ctx), _acao(ctx), _sinal_risco(ctx)
    return (
        f"Ola, {nome}.\n\n"
        f"Aqui e a coordenacao do curso de {curso}. {sinal}\n"
        f"Recomendamos: {acao}.\n\n"
        f"Conte com a gente — responda este e-mail ou procure a secretaria.\n\n"
        f"Atenciosamente,\nCoordenacao Academica"
    )


def render_sms(ctx: MessageContext) -> str:
    nome, acao = _primeiro_nome(ctx), _acao(ctx)
    msg = f"{nome}, a coordenacao quer te ajudar: {acao}. Responda ou procure a secretaria."
    if len(msg) > SMS_MAX_LEN:
        msg = msg[: SMS_MAX_LEN - 3] + "..."
    return msg
