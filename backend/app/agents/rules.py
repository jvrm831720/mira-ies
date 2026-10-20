"""Regras de escolha de canal e anti-spam do orquestrador de retencao.

Logica pura (sem DB/rede) de proposito — e o que faz o comportamento do
orquestrador testavel com testes unitarios rapidos.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal

Channel = Literal["whatsapp", "email", "sms"]


def decide_channels(
    *,
    risk_level: str,
    telefone: str | None,
    email: str | None,
    prefer_whatsapp_medio: bool = False,
) -> list[Channel]:
    """Retorna os canais candidatos em ordem de prioridade para este aluno.

    O orquestrador tenta cada um ate o primeiro envio bem-sucedido — assim
    "whatsapp prioritario, cai para e-mail, cai para sms" funciona tanto para
    ausencia de dado de contato quanto para falha de envio em tempo real.
    Risco baixo nunca dispara. Lista vazia tambem ocorre quando nao ha
    nenhum contato (telefone/email) cadastrado.
    """
    has_phone = bool(telefone)
    has_email = bool(email)

    if risk_level == "baixo":
        return []

    if risk_level == "critico":
        order: list[Channel] = []
        if has_phone:
            order.append("whatsapp")
        if has_email:
            order.append("email")
        if has_phone:
            order.append("sms")
        return order

    # medio (e qualquer outro nivel nao reconhecido cai aqui, tratado como nao-critico)
    order = []
    if prefer_whatsapp_medio and has_phone:
        order.append("whatsapp")
    if has_email:
        order.append("email")
    if has_phone and "whatsapp" not in order:
        order.append("whatsapp")
    return order


def skip_reason_for_no_channel(risk_level: str) -> str:
    return "risco baixo — sem disparo" if risk_level == "baixo" else "missing_contact"


def check_anti_spam(
    *,
    channel: Channel,
    now: datetime,
    last_contact_at_this_channel: datetime | None,
    contacts_last_7_days: int,
    min_hours_between_contact: int,
    max_contacts_per_week: int,
) -> tuple[bool, str | None]:
    """Retorna (permitido, motivo_do_bloqueio). Motivo None quando permitido."""
    if contacts_last_7_days >= max_contacts_per_week:
        return False, f"anti-spam: limite de {max_contacts_per_week} mensagens/7 dias atingido"
    if last_contact_at_this_channel is not None:
        cutoff = now - timedelta(hours=min_hours_between_contact)
        if last_contact_at_this_channel >= cutoff:
            return False, f"anti-spam: ja contatado via {channel} ha menos de {min_hours_between_contact}h"
    return True, None
