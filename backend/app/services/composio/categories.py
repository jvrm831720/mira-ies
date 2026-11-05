"""Curated MIRA taxonomy for Composio integrations.

Composio toolkits are catalogued separately from native MIRA channel providers.
A toolkit being listed here never enables it or grants an agent permission to use it.
"""
from __future__ import annotations

from typing import Any

from app.core.config import Settings, get_settings


COMMUNICATION_TOOLKITS: dict[str, dict[str, str]] = {
    "gmail": {"name": "Gmail", "kind": "email"},
    "outlook": {"name": "Outlook", "kind": "email"},
    "slack": {"name": "Slack", "kind": "team_messaging"},
    "microsoft_teams": {"name": "Microsoft Teams", "kind": "team_messaging"},
    "zoom": {"name": "Zoom", "kind": "meetings"},
    "zoom_chat": {"name": "Zoom Team Chat", "kind": "team_messaging"},
    "aircall": {"name": "Aircall", "kind": "telephony"},
}


CRM_TOOLKITS: dict[str, dict[str, str]] = {
    "hubspot": {"name": "HubSpot", "kind": "crm"},
    "salesforce": {"name": "Salesforce", "kind": "crm"},
    "pipedrive": {"name": "Pipedrive", "kind": "crm"},
    "dynamics365": {"name": "Dynamics 365", "kind": "crm"},
}

DOCUMENT_TOOLKITS: dict[str, dict[str, str]] = {
    "googledrive": {"name": "Google Drive", "kind": "cloud_storage"},
    "one_drive": {"name": "OneDrive", "kind": "cloud_storage"},
    "share_point": {"name": "SharePoint", "kind": "document_collaboration"},
    "dropbox": {"name": "Dropbox", "kind": "cloud_storage"},
}

DATA_ANALYSIS_TOOLKITS: dict[str, dict[str, str]] = {
    "googlesheets": {"name": "Google Sheets", "kind": "spreadsheet"},
    "excel": {"name": "Microsoft Excel", "kind": "spreadsheet"},
    "airtable": {"name": "Airtable", "kind": "structured_database"},
}


SUPPORT_TOOLKITS: dict[str, dict[str, str]] = {
    "zendesk": {"name": "Zendesk", "kind": "helpdesk"},
    "freshdesk": {"name": "Freshdesk", "kind": "helpdesk"},
    "intercom": {"name": "Intercom", "kind": "customer_messaging"},
    "zoho_desk": {"name": "Zoho Desk", "kind": "helpdesk"},
}


PRODUCTIVITY_TOOLKITS: dict[str, dict[str, str]] = {
    "asana": {"name": "Asana", "kind": "project_management"},
    "trello": {"name": "Trello", "kind": "kanban"},
    "clickup": {"name": "ClickUp", "kind": "work_management"},
    "notion": {"name": "Notion", "kind": "knowledge_and_tasks"},
}


SCHEDULING_TOOLKITS: dict[str, dict[str, str]] = {
    "googlecalendar": {"name": "Google Calendar", "kind": "calendar"},
    "calendly": {"name": "Calendly", "kind": "appointment_booking"},
    "cal": {"name": "Cal.com", "kind": "appointment_booking"},
}


MARKETING_TOOLKITS: dict[str, dict[str, str]] = {
    "mailchimp": {"name": "Mailchimp", "kind": "email_marketing"},
    "brevo": {"name": "Brevo", "kind": "multichannel_marketing"},
    "active_campaign": {"name": "ActiveCampaign", "kind": "marketing_automation"},
    "customerio": {"name": "Customer.io", "kind": "customer_engagement"},
}


FINANCE_TOOLKITS: dict[str, dict[str, str]] = {
    "xero": {"name": "Xero", "kind": "accounting"},
    "zoho_books": {"name": "Zoho Books", "kind": "accounting"},
    "freshbooks": {"name": "FreshBooks", "kind": "accounting"},
    "netsuite": {"name": "Oracle NetSuite", "kind": "financial_erp"},
    "sage_intacct": {"name": "Sage Intacct", "kind": "financial_management"},
    "odoo": {"name": "Odoo", "kind": "erp_finance"},
    "erpnext": {"name": "ERPNext", "kind": "erp_finance"},
    "stripe": {"name": "Stripe", "kind": "payment_processing"},
}


# Omie is intentionally represented as a custom integration, not a Composio
# toolkit: it was not present in the official Composio toolkit catalog when
# this category was curated. A custom adapter/toolkit must be implemented
# and reviewed before any connection or execution is possible.
OMIE_CUSTOM_INTEGRATION: dict[str, Any] = {
    "slug": "omie",
    "name": "Omie",
    "kind": "financial_erp",
    "integration_type": "custom",
    "status": "requires_custom_toolkit",
    "composio_toolkit_slug": None,
}


def annotate_toolkit(item: dict[str, Any]) -> dict[str, Any]:
    """Attach MIRA category metadata using verified Composio toolkit slugs."""
    slug = str(item.get("slug") or "").strip().lower()
    for category_slug, category_label, toolkits in (
        ("communication", "Comunicação", COMMUNICATION_TOOLKITS),
        ("crm", "CRM e relacionamento", CRM_TOOLKITS),
        ("documents", "Documentos e arquivos", DOCUMENT_TOOLKITS),
        ("productivity", "Produtividade e tarefas", PRODUCTIVITY_TOOLKITS),
        ("data_analysis", "Dados, planilhas e análise", DATA_ANALYSIS_TOOLKITS),
        ("support", "Atendimento e suporte", SUPPORT_TOOLKITS),
        ("scheduling", "Agenda e agendamento", SCHEDULING_TOOLKITS),
        ("marketing", "Marketing institucional", MARKETING_TOOLKITS),
        ("finance", "Financeiro e gestão financeira", FINANCE_TOOLKITS),
    ):
        metadata = toolkits.get(slug)
        if metadata:
            return {
                **item,
                "mira_category": category_slug,
                "mira_category_label": category_label,
                "mira_channel": metadata["kind"],
            }
    return {**item, "mira_category": None, "mira_category_label": None}


def crm_category() -> dict[str, Any]:
    """Return the curated CRM category without enabling any toolkit."""
    return {
        "slug": "crm",
        "name": "CRM e relacionamento",
        "description": (
            "Gestão de contatos, contas, histórico de relacionamento, "
            "oportunidades, negociações e atividades."
        ),
        "composio_toolkits": [
            {"slug": slug, **metadata}
            for slug, metadata in CRM_TOOLKITS.items()
        ],
        "native_channels": [],
    }


def documents_category() -> dict[str, Any]:
    """Return the curated document category without enabling any toolkit."""
    return {
        "slug": "documents",
        "name": "Documentos e arquivos",
        "description": (
            "Localização, consulta e gestão de arquivos autorizados em "
            "repositórios corporativos e espaços de colaboração."
        ),
        "composio_toolkits": [
            {"slug": slug, **metadata}
            for slug, metadata in DOCUMENT_TOOLKITS.items()
        ],
        "native_channels": [],
    }


def data_analysis_category() -> dict[str, Any]:
    """Return data and spreadsheet toolkits without enabling any toolkit."""
    return {
        "slug": "data_analysis",
        "name": "Dados, planilhas e análise",
        "description": (
            "Consulta e organização de planilhas, tabelas e bases estruturadas "
            "para análises e relatórios auxiliares."
        ),
        "composio_toolkits": [
            {"slug": slug, **metadata}
            for slug, metadata in DATA_ANALYSIS_TOOLKITS.items()
        ],
        "native_channels": [],
    }


def support_category() -> dict[str, Any]:
    """Return customer support toolkits without enabling any toolkit."""
    return {
        "slug": "support",
        "name": "Atendimento e suporte",
        "description": (
            "Consulta e gestão de tickets, solicitações, filas, conversas "
            "e histórico de atendimento em plataformas de suporte."
        ),
        "composio_toolkits": [
            {"slug": slug, **metadata}
            for slug, metadata in SUPPORT_TOOLKITS.items()
        ],
        "native_channels": [],
    }


def scheduling_category() -> dict[str, Any]:
    """Return scheduling toolkits without enabling any toolkit."""
    return {
        "slug": "scheduling",
        "name": "Agenda e agendamento",
        "description": (
            "Consulta de disponibilidade, organização de calendários, "
            "criação e gestão de compromissos e links de agendamento."
        ),
        "composio_toolkits": [
            {"slug": slug, **metadata}
            for slug, metadata in SCHEDULING_TOOLKITS.items()
        ],
        "native_channels": [],
    }


def marketing_category() -> dict[str, Any]:
    """Return marketing toolkits without enabling campaigns or automations."""
    return {
        "slug": "marketing",
        "name": "Marketing institucional",
        "description": (
            "Gestão de públicos e preferências, campanhas, jornadas de relacionamento "
            "e análise de engajamento em canais de marketing."
        ),
        "composio_toolkits": [
            {"slug": slug, **metadata}
            for slug, metadata in MARKETING_TOOLKITS.items()
        ],
        "native_channels": [],
    }


def productivity_category() -> dict[str, Any]:
    """Return productivity toolkits without enabling any toolkit."""
    return {
        "slug": "productivity",
        "name": "Produtividade e tarefas",
        "description": (
            "Organização de projetos, tarefas, responsáveis, prazos, "
            "quadros de trabalho e bases de conhecimento."
        ),
        "composio_toolkits": [
            {"slug": slug, **metadata}
            for slug, metadata in PRODUCTIVITY_TOOLKITS.items()
        ],
        "native_channels": [],
    }


def annotate_communication_toolkit(item: dict[str, Any]) -> dict[str, Any]:
    """Attach MIRA's category metadata without changing the live Composio record."""
    return annotate_toolkit(item)


def native_communication_channels(settings: Settings | None = None) -> list[dict[str, Any]]:
    """Describe existing native MIRA channels without exposing provider secrets."""
    config = settings or get_settings()
    return [
        {
            "slug": "whatsapp",
            "name": "WhatsApp",
            "kind": "messaging",
            "integration_type": "native",
            "providers": [
                {
                    "slug": "waha",
                    "configured": bool(config.waha_api_url and config.waha_api_key),
                },
                {
                    "slug": "evolution",
                    "configured": bool(config.evolution_api_url and config.evolution_api_key),
                },
            ],
        },
        {
            "slug": "email_delivery",
            "name": "E-mail transacional",
            "kind": "email_delivery",
            "integration_type": "native",
            "providers": [
                {
                    "slug": "resend",
                    "configured": bool(config.resend_api_key and config.email_from),
                },
            ],
        },
        {
            "slug": "sms",
            "name": "SMS",
            "kind": "sms",
            "integration_type": "native",
            "providers": [
                {
                    "slug": "twilio",
                    "configured": bool(
                        config.twilio_account_sid
                        and config.twilio_auth_token
                        and config.twilio_from
                    ),
                },
            ],
        },
    ]


def communication_category(settings: Settings | None = None) -> dict[str, Any]:
    """Return the communication category split into Composio and native channels."""
    return {
        "slug": "communication",
        "name": "Comunicação",
        "description": (
            "E-mail, mensageria, colaboração, reuniões e telefonia "
            "para relacionamento com alunos, responsáveis, clientes e equipes."
        ),
        "composio_toolkits": [
            {"slug": slug, **metadata}
            for slug, metadata in COMMUNICATION_TOOLKITS.items()
        ],
        "native_channels": native_communication_channels(settings),
    }



def finance_category() -> dict[str, Any]:
    """Return finance toolkits and explicitly identified custom integrations."""
    return {
        "slug": "finance",
        "name": "Financeiro e gestão financeira",
        "description": (
            "Consulta e gestão financeira, contas a pagar e receber, faturamento, "
            "despesas, pagamentos, conciliação, fluxo de caixa e relatórios."
        ),
        "composio_toolkits": [
            {"slug": slug, **metadata}
            for slug, metadata in FINANCE_TOOLKITS.items()
        ],
        "custom_integrations": [OMIE_CUSTOM_INTEGRATION.copy()],
        "native_channels": [],
    }
