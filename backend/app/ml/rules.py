"""
Camada de regras de negocio hibrida.

Combina sinais claros de risco (regras) com a probabilidade do modelo ML.
"""

from __future__ import annotations

from typing import Any

THRESHOLDS = {
    "atraso_critico_dias": 30,
    "atraso_grave_dias": 15,
    "login_critico_dias": 21,
    "login_alerta_dias": 14,
    "presenca_critica": 50.0,
    "presenca_baixa": 70.0,
    "nota_critica": 4.0,
    "nota_baixa": 6.0,
}


def apply_business_rules(
    features: dict[str, float],
    model_score: float,
) -> dict[str, Any]:
    flags: list[str] = []
    actions: list[str] = []
    boost = 0.0

    dias_atraso = features.get("dias_atraso_boleto", 0)
    dias_login = features.get("dias_sem_login", 0)
    presenca = features.get("presenca_percentual", 100)
    nota = features.get("nota_media", 7)
    recorrencia = features.get("recorrencia_atrasos", 0)
    is_early = features.get("is_early_semester", 0)
    combo = features.get("combo_critico", 0)
    reprovacoes = features.get("reprovacoes", 0)

    if dias_atraso >= THRESHOLDS["atraso_critico_dias"]:
        flags.append("atraso_financeiro_critico")
        actions.append("Acionar setor financeiro + oferta de renegociacao")
        boost += 15
    elif dias_atraso >= THRESHOLDS["atraso_grave_dias"]:
        flags.append("atraso_financeiro_grave")
        actions.append("Contato financeiro preventivo (boleto em aberto)")
        boost += 8

    if recorrencia >= 3:
        flags.append("reincidencia_atrasos")
        actions.append("Avaliar perfil de inadimplencia recorrente")
        boost += 5

    if dias_login >= THRESHOLDS["login_critico_dias"]:
        flags.append("abandono_digital")
        actions.append("Disparo WhatsApp de reengajamento + checagem de acesso ao AVA")
        boost += 12
    elif dias_login >= THRESHOLDS["login_alerta_dias"]:
        flags.append("engajamento_baixo")
        actions.append("Lembrete de atividades pendentes no AVA")
        boost += 5

    if nota < THRESHOLDS["nota_critica"]:
        flags.append("desempenho_critico")
        actions.append("Encaminhar para tutoria / plantao de duvidas")
        boost += 12
    elif nota < THRESHOLDS["nota_baixa"]:
        flags.append("desempenho_baixo")
        actions.append("Acompanhamento pedagogico preventivo")
        boost += 5

    if presenca < THRESHOLDS["presenca_critica"]:
        flags.append("frequencia_critica")
        actions.append("Verificar faltas e risco de dependencia")
        boost += 10
    elif presenca < THRESHOLDS["presenca_baixa"]:
        flags.append("frequencia_baixa")
        boost += 4

    if reprovacoes >= 2:
        flags.append("multiplas_reprovacoes")
        actions.append("Plano de estudos e acompanhamento de dependencias")
        boost += 6

    if combo >= 1:
        flags.append("combo_financeiro_engajamento")
        actions.append("Prioridade maxima na fila do coordenador")
        boost += 10

    if is_early and (dias_atraso > 15 or dias_login > 14 or nota < 6):
        flags.append("risco_inicio_curso")
        actions.append("Intervencao precoce (1o/2o semestre)")
        boost += 6

    adjusted = min(100.0, max(0.0, model_score + boost))

    if adjusted >= 70 or len([f for f in flags if "critico" in f or "abandono" in f or "combo" in f]) >= 2:
        level = "critico"
    elif adjusted >= 40:
        level = "medio"
    else:
        level = "baixo"

    model_level = "critico" if model_score >= 70 else ("medio" if model_score >= 40 else "baixo")
    if model_level == level and flags:
        confidence = "alta"
    elif model_level == level:
        confidence = "media"
    elif abs(model_score - adjusted) > 20:
        confidence = "revisar"
    else:
        confidence = "media"

    seen = set()
    unique_actions = []
    for a in actions:
        if a not in seen:
            seen.add(a)
            unique_actions.append(a)
    if not unique_actions and level == "baixo":
        unique_actions.append("Monitoramento rotineiro")

    return {
        "adjusted_score": round(adjusted, 1),
        "model_score": round(model_score, 1),
        "risk_level": level,
        "rule_flags": flags,
        "rule_boost": round(boost, 1),
        "recommended_actions": unique_actions[:5],
        "confidence": confidence,
    }
