"""Initial recommendation layer for retention campaign opportunities.

This version is deterministic and evidence-based. It does not generate or send
messages; it creates explainable campaign briefs for human review.
"""
from __future__ import annotations

from typing import Any


_RECOMMENDATIONS: dict[str, dict[str, Any]] = {
    "risk_critical": {
        "objective": "Priorizar contato individual para reduzir barreiras à permanência.",
        "strategy": "Acolhimento prioritário com encaminhamento para atendimento humano.",
        "channels": ["whatsapp", "email"],
        "cadence_days": [0, 2],
        "message_brief": "Mensagem acolhedora, com convite para conversar e opção clara de atendimento humano.",
        "rationale": "O grupo reúne alunos com classificação de risco crítico e score utilizável.",
        "safeguards": ["Respeitar opt-out e preferências por canal.", "Evitar linguagem alarmista ou afirmar que a evasão é certa.", "Priorizar atendimento humano para casos críticos."],
    },
    "risk_medium": {
        "objective": "Antecipar dificuldades e oferecer apoio antes de uma escalada do risco.",
        "strategy": "Contato preventivo com orientação e convite para identificar necessidades.",
        "channels": ["whatsapp", "email"],
        "cadence_days": [0, 4, 10],
        "message_brief": "Mensagem breve de apoio, com pergunta aberta e caminhos de suporte acadêmico ou financeiro.",
        "rationale": "O grupo reúne alunos com classificação de risco médio e score utilizável.",
        "safeguards": ["Respeitar opt-out e preferências por canal.", "Não apresentar a classificação interna de risco ao aluno.", "Interromper a régua quando houver resposta ou atendimento aberto."],
    },
    "financial_delay": {
        "objective": "Identificar barreiras financeiras e apresentar caminhos regulares de negociação.",
        "strategy": "Acolhimento financeiro com encaminhamento para os canais oficiais da instituição.",
        "channels": ["whatsapp", "email"],
        "cadence_days": [0, 3, 7],
        "message_brief": "Comunicação respeitosa, sem exposição de dívida em notificações, com convite para consultar opções nos canais oficiais.",
        "rationale": "O sinal financeiro registra atraso igual ou superior ao limiar documentado; dados ausentes não são tratados como atraso.",
        "safeguards": ["Validar saldo e situação financeira antes de qualquer oferta.", "Não incluir valores ou detalhes sensíveis em notificações.", "Respeitar opt-out e preferências por canal."],
    },
    "days_without_login_elevated": {
        "objective": "Reengajar o aluno e identificar dificuldades de acesso ou acompanhamento acadêmico.",
        "strategy": "Contato de suporte com orientação para acesso e oferta de ajuda acadêmica.",
        "channels": ["whatsapp", "email"],
        "cadence_days": [0, 3, 7],
        "message_brief": "Mensagem de apoio para confirmar se o aluno precisa de ajuda para acessar o ambiente ou acompanhar as atividades.",
        "rationale": "O sinal registra dias sem login acima do limiar definido; ausência de dado permanece indeterminada.",
        "safeguards": ["Não presumir desinteresse ou abandono.", "Confirmar disponibilidade do ambiente e eventuais falhas técnicas.", "Respeitar opt-out e preferências por canal."],
    },
    "risk_increase": {
        "objective": "Intervir cedo diante de uma piora observada em avaliações comparáveis.",
        "strategy": "Contato consultivo, com revisão do histórico e encaminhamento personalizado.",
        "channels": ["whatsapp", "email"],
        "cadence_days": [0, 2, 6],
        "message_brief": "Mensagem de acompanhamento que oferece escuta e atendimento, sem revelar score ou inferir causa.",
        "rationale": "O grupo exige avaliações históricas comparáveis e aumento relevante de risco.",
        "safeguards": ["Confirmar comparabilidade entre avaliações.", "Não atribuir causalidade a um evento isolado.", "Respeitar opt-out e preferências por canal."],
    },
    "multiple_active_signals": {
        "objective": "Coordenar atendimento prioritário quando mais de um sinal operacional está ativo.",
        "strategy": "Plano de contato integrado, com um responsável e prevenção de mensagens duplicadas.",
        "channels": ["whatsapp", "email"],
        "cadence_days": [0, 3],
        "message_brief": "Contato único e acolhedor, consolidando o convite para atendimento sem listar sinais internos.",
        "rationale": "O grupo exige pelo menos dois sinais operacionais definitivamente ativos; sinais indeterminados não contam como ativos.",
        "safeguards": ["Deduplicar alunos presentes em vários grupos.", "Consultar intervenções e contatos recentes antes de incluir o aluno.", "Respeitar opt-out e preferências por canal."],
    },
    "missing_score": {
        "objective": "Recuperar cobertura e qualidade dos dados para permitir uma avaliação confiável.",
        "strategy": "Ação interna de saneamento e atualização de dados; não iniciar comunicação automática com base na ausência de score.",
        "channels": ["operacao_interna"],
        "cadence_days": [],
        "message_brief": "Não gerar mensagem ao aluno nesta etapa. Abrir tarefa interna para verificar dados e reprocessar a avaliação.",
        "rationale": "A ausência de score representa lacuna de cobertura, não baixo risco nem evidência de evasão.",
        "safeguards": ["Bloquear disparo automático nesta oportunidade.", "Não classificar o aluno como baixo risco.", "Reavaliar somente após dados válidos."],
    },
}


def build_campaign_opportunities(summary: dict[str, Any]) -> list[dict[str, Any]]:
    """Turn the canonical seven-group summary into explainable campaign briefs."""
    opportunities: list[dict[str, Any]] = []
    for group in summary.get("groups", []):
        recommendation = _RECOMMENDATIONS.get(group.get("id"))
        if recommendation is None:
            continue
        matched = int(group.get("matched_count") or 0)
        indeterminate = int(group.get("indeterminate_count") or 0)
        if matched == 0 and indeterminate == 0:
            continue
        safeguards = list(recommendation["safeguards"])
        if group.get("coverage", {}).get("complete") is not True:
            safeguards.append("Cobertura incompleta: revisar casos indeterminados antes de aprovar o público.")
        opportunities.append(
            {
                "group_id": group["id"],
                "group_name": group["name"],
                "catalog_version": summary.get("catalog_version", "1.0.0"),
                "matched_count": matched,
                "indeterminate_count": indeterminate,
                "estimated_reach": {
                    "upper_bound": matched,
                    "unit": "students",
                    "validated_contacts": False,
                    "note": "Estimativa bruta do grupo; ainda não desconta opt-out, preferências, contatos inválidos ou intervenções recentes.",
                },
                "objective": recommendation["objective"],
                "strategy": recommendation["strategy"],
                "recommended_channels": list(recommendation["channels"]),
                "cadence_days": list(recommendation["cadence_days"]),
                "message_brief": recommendation["message_brief"],
                "justification": recommendation["rationale"],
                "safeguards": safeguards,
                "automatic_outreach_allowed": group["id"] != "missing_score",
                "recommendation_engine": "signals-and-rules-v1",
            }
        )
    return opportunities
