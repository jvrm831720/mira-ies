"""Agente de canal E-mail — dry-run por padrao, Resend se RESEND_API_KEY configurado."""

from __future__ import annotations

import re

from app.agents.base import MessageContext, SendResult
from app.agents.providers.dry_run import dry_run_send
from app.agents.providers.resend_provider import send_email_resend
from app.agents.templates import render_email_body, render_email_subject
from app.core.config import get_settings

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_valid_email(raw: str | None) -> bool:
    return bool(raw) and bool(_EMAIL_RE.match(raw.strip()))


class EmailAgent:
    channel = "email"

    def render(self, ctx: MessageContext) -> str:
        return render_email_body(ctx)

    def render_subject(self, ctx: MessageContext) -> str:
        return render_email_subject(ctx)

    async def send(
        self,
        ctx: MessageContext,
        message: str,
        *,
        dry_run: bool,
        idempotency_key: str | None = None,
    ) -> SendResult:
        if not is_valid_email(ctx.email):
            return SendResult(
                ok=False,
                channel="email",
                provider="dry_run" if dry_run else "resend",
                error="email invalido ou ausente",
                outcome="confirmed_failure",
            )
        settings = get_settings()
        if dry_run or not settings.resend_api_key:
            return await dry_run_send(channel="email", to=ctx.email, message=message)
        return await send_email_resend(
            to=ctx.email,
            subject=self.render_subject(ctx),
            body=message,
            idempotency_key=idempotency_key,
        )
