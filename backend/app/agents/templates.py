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


def _safe_value(value: object, max_length: int = 100) -> str:
    return " ".join(str(value).replace("\\n", " ").replace("\\r", " ").split())[:max_length]


def _personalized_facts(ctx: MessageContext) -> str:
    """Render selected properties only; custom fields require an explicit message_fields opt-in."""
    properties = ctx.behavior_properties or {}
    selected = set(properties.get("message_fields") or [])
    facts: list[str] = []

    missed_class = properties.get("last_class_missed")
    if "last_class_missed" in selected and missed_class:
        facts.append(f"Notamos que você faltou à aula de {_safe_value(missed_class, 90)} recentemente.")

    missed_count = properties.get("missed_classes_this_week")
    if "missed_classes_this_week" in selected and isinstance(missed_count, int) and not isinstance(missed_count, bool):
        if missed_count > 0:
            facts.append(f"Há {missed_count} falta(s) registrada(s) nesta semana.")

    module = properties.get("current_module")
    progress = properties.get("module_progress_pct")
    if module and "current_module" in selected and "module_progress_pct" in selected and isinstance(progress, (int, float)):
        facts.append(f"Seu progresso no módulo {_safe_value(module, 80)} está em {progress:g}%.")
    elif module and "current_module" in selected:
        facts.append(f"Você está no módulo {_safe_value(module, 80)}.")

    activity = properties.get("recent_activity")
    if "recent_activity" in selected and activity:
        facts.append(f"Atividade recente registrada: {_safe_value(activity, 90)}.")

    last_activity_at = properties.get("last_activity_at")
    if "last_activity_at" in selected and last_activity_at:
        facts.append(f"Última atividade registrada em {_safe_value(last_activity_at, 35)}.")

    custom = properties.get("custom_properties") or {}
    for field in sorted(selected):
        if not field.startswith("custom_properties."):
            continue
        key = field.split(".", 1)[1]
        value = custom.get(key)
        if value is None or value == "":
            continue
        label = key.replace("_", " ")
        facts.append(f"Informação atualizada — {_safe_value(label, 40)}: {_safe_value(value, 70)}.")

    return " ".join(facts[:3])


def render_whatsapp(ctx: MessageContext) -> str:
    nome, curso, acao, sinal = _primeiro_nome(ctx), _curso(ctx), _acao(ctx), _sinal_risco(ctx)
    personal = _personalized_facts(ctx)
    if ctx.risk_level == "critico":
        return (
            f"Ola, {nome}. Aqui e a coordenacao do curso de {curso}. {sinal} {personal} "
            f"Queremos te ajudar — {acao}. Responda esta mensagem ou procure a secretaria. "
            f"Estamos com voce."
        )
    return f"Ola, {nome}! Aqui e a coordenacao de {curso}. {sinal} {personal} Que tal {acao}? Estamos aqui se precisar."


def render_email_subject(ctx: MessageContext) -> str:
    curso = _curso(ctx)
    if ctx.risk_level == "critico":
        return f"{curso} — queremos te ajudar a continuar"
    return f"{curso} — como podemos te apoiar"


def render_email_body(ctx: MessageContext) -> str:
    nome, curso, acao, sinal = _primeiro_nome(ctx), _curso(ctx), _acao(ctx), _sinal_risco(ctx)
    personal = _personalized_facts(ctx)
    return (
        f"Ola, {nome}.\n\n"
        f"Aqui e a coordenacao do curso de {curso}. {sinal}\n"
        f"{personal}\n"
        f"Recomendamos: {acao}.\n\n"
        f"Conte com a gente — responda este e-mail ou procure a secretaria.\n\n"
        f"Atenciosamente,\nCoordenacao Academica"
    )


def render_sms(ctx: MessageContext) -> str:
    nome, acao = _primeiro_nome(ctx), _acao(ctx)
    personal = _personalized_facts(ctx)
    msg = f"{nome}, a coordenacao quer te ajudar. {personal} {acao}. Responda ou procure a secretaria."
    if len(msg) > SMS_MAX_LEN:
        msg = msg[: SMS_MAX_LEN - 3] + "..."
    return msg
