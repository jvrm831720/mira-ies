"""Contratos comuns dos agentes de canal do sistema de retencao."""

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel

Channel = Literal["whatsapp", "email", "sms"]


class SendResult(BaseModel):
    ok: bool
    channel: Channel
    provider: str  # "dry_run" | "evolution" | "resend" | "twilio"
    external_id: str | None = None
    error: str | None = None
    dry_run: bool = False


class MessageContext(BaseModel):
    """O que um agente de canal precisa para montar e enviar uma mensagem."""

    tenant_id: str
    student_id: str
    matricula: str
    nome: str
    curso: str | None = None
    risk_level: str
    risk_score: float | None = None
    top_factor_label: str | None = None
    recommended_action: str | None = None
    telefone: str | None = None
    email: str | None = None


class ChannelAgent(Protocol):
    channel: Channel

    def render(self, ctx: MessageContext) -> str: ...

    async def send(self, ctx: MessageContext, message: str, *, dry_run: bool) -> SendResult: ...
