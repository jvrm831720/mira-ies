"""Registry of implemented channel/template pairs used by retention campaigns."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from app.agents.base import MessageContext
from app.agents.templates import render_email_body, render_email_subject, render_sms, render_whatsapp


@dataclass(frozen=True)
class RenderedCampaignTemplate:
    body: str
    subject: str | None = None


TemplateRenderer = Callable[[MessageContext], RenderedCampaignTemplate]


def _with_risk(ctx: MessageContext, risk_level: str) -> MessageContext:
    return ctx.model_copy(update={"risk_level": risk_level})


def _whatsapp_dynamic(ctx: MessageContext) -> RenderedCampaignTemplate:
    return RenderedCampaignTemplate(body=render_whatsapp(ctx))


def _whatsapp_critical(ctx: MessageContext) -> RenderedCampaignTemplate:
    return RenderedCampaignTemplate(body=render_whatsapp(_with_risk(ctx, "critico")))


def _whatsapp_default(ctx: MessageContext) -> RenderedCampaignTemplate:
    return RenderedCampaignTemplate(body=render_whatsapp(_with_risk(ctx, "medio")))


def _email_dynamic(ctx: MessageContext) -> RenderedCampaignTemplate:
    return RenderedCampaignTemplate(body=render_email_body(ctx), subject=render_email_subject(ctx))


def _email_critical(ctx: MessageContext) -> RenderedCampaignTemplate:
    template_ctx = _with_risk(ctx, "critico")
    return RenderedCampaignTemplate(
        body=render_email_body(template_ctx), subject=render_email_subject(template_ctx)
    )


def _email_default(ctx: MessageContext) -> RenderedCampaignTemplate:
    template_ctx = _with_risk(ctx, "medio")
    return RenderedCampaignTemplate(
        body=render_email_body(template_ctx), subject=render_email_subject(template_ctx)
    )


def _sms_default(ctx: MessageContext) -> RenderedCampaignTemplate:
    return RenderedCampaignTemplate(body=render_sms(ctx))


TEMPLATE_REGISTRY: dict[tuple[str, str], TemplateRenderer] = {
    ("whatsapp", "retention_v1"): _whatsapp_dynamic,
    ("whatsapp", "critico_v1"): _whatsapp_critical,
    ("whatsapp", "whatsapp_critical_v1"): _whatsapp_critical,
    ("whatsapp", "whatsapp_default_v1"): _whatsapp_default,
    ("email", "retention_v1"): _email_dynamic,
    ("email", "score_alto_v1"): _email_critical,
    ("email", "email_critical_v1"): _email_critical,
    ("email", "email_default_v1"): _email_default,
    ("sms", "retention_v1"): _sms_default,
    ("sms", "sms_default_v1"): _sms_default,
}


def validate_campaign_template(channel: str, template_id: str) -> None:
    if (channel, template_id) not in TEMPLATE_REGISTRY:
        raise ValueError(
            f"Template não suportado: channel={channel!r}, template_id={template_id!r}."
        )


def render_campaign_template(
    ctx: MessageContext, channel: str, template_id: str
) -> RenderedCampaignTemplate:
    validate_campaign_template(channel, template_id)
    return TEMPLATE_REGISTRY[(channel, template_id)](ctx)
