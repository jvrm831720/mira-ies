"""
Camada de regras de negócio híbrida.
Cada ajuste é retornado como evento explicável, com evidência e delta explícitos.
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


def apply_business_rules(features: dict[str, float], model_score: float) -> dict[str, Any]:
    # Deriva somente variáveis determinísticas de campos-base presentes.
    features = dict(features)
    if "is_early_semester" not in features and features.get("semestre") is not None:
        features["is_early_semester"] = float(features["semestre"] <= 2)
    if "combo_critico" not in features and all(
        features.get(key) is not None for key in ("dias_atraso_boleto", "dias_sem_login")
    ):
        features["combo_critico"] = float(
            features["dias_atraso_boleto"] > 15 and features["dias_sem_login"] > 14
        )
    required = (
        "dias_atraso_boleto", "dias_sem_login", "presenca_percentual",
        "nota_media", "recorrencia_atrasos", "semestre",
        "is_early_semester", "combo_critico", "reprovacoes",
    )
    missing = [key for key in required if key not in features or features[key] is None]
    if missing:
        raise ValueError(f"Regras bloqueadas por features ausentes: {', '.join(missing)}")

    flags: list[str] = []
    actions: list[str] = []
    adjustments: list[dict[str, Any]] = []
    boost = 0.0

    def add(flag: str, description: str, delta: float, evidence: dict[str, Any], action: str | None = None):
        nonlocal boost
        flags.append(flag)
        boost += delta
        adjustments.append({
            "flag": flag,
            "description": description,
            "delta_points": delta,
            "evidence": evidence,
            "recommendation": action,
            "source": "business_rule",
        })
        if action:
            actions.append(action)

    atraso = features["dias_atraso_boleto"]
    login = features["dias_sem_login"]
    presenca = features["presenca_percentual"]
    nota = features["nota_media"]
    recorrencia = features["recorrencia_atrasos"]
    reprovacoes = features["reprovacoes"]
    early = bool(features["is_early_semester"])
    combo = bool(features["combo_critico"])

    if atraso >= THRESHOLDS["atraso_critico_dias"]:
        add("atraso_financeiro_critico", "Atraso financeiro crítico", 15,
            {"field": "dias_atraso_boleto", "observed": atraso, "threshold": THRESHOLDS["atraso_critico_dias"], "operator": ">="},
            "Acionar setor financeiro e avaliar oferta de renegociação")
    elif atraso >= THRESHOLDS["atraso_grave_dias"]:
        add("atraso_financeiro_grave", "Atraso financeiro grave", 8,
            {"field": "dias_atraso_boleto", "observed": atraso, "threshold": THRESHOLDS["atraso_grave_dias"], "operator": ">="},
            "Contato financeiro preventivo sobre o boleto em aberto")
    if recorrencia >= 3:
        add("reincidencia_atrasos", "Recorrência de atrasos", 5,
            {"field": "recorrencia_atrasos", "observed": recorrencia, "threshold": 3, "operator": ">="},
            "Avaliar perfil de inadimplência recorrente")
    if login >= THRESHOLDS["login_critico_dias"]:
        add("abandono_digital", "Ausência prolongada de acesso ao AVA", 12,
            {"field": "dias_sem_login", "observed": login, "threshold": THRESHOLDS["login_critico_dias"], "operator": ">="},
            "Verificar acesso ao AVA e realizar contato de reengajamento")
    elif login >= THRESHOLDS["login_alerta_dias"]:
        add("engajamento_baixo", "Tempo sem acesso acima do limite de alerta", 5,
            {"field": "dias_sem_login", "observed": login, "threshold": THRESHOLDS["login_alerta_dias"], "operator": ">="},
            "Lembrar o aluno das atividades pendentes no AVA")
    if nota < THRESHOLDS["nota_critica"]:
        add("desempenho_critico", "Nota média em faixa crítica", 12,
            {"field": "nota_media", "observed": nota, "threshold": THRESHOLDS["nota_critica"], "operator": "<"},
            "Encaminhar para tutoria ou plantão de dúvidas")
    elif nota < THRESHOLDS["nota_baixa"]:
        add("desempenho_baixo", "Nota média abaixo da faixa esperada", 5,
            {"field": "nota_media", "observed": nota, "threshold": THRESHOLDS["nota_baixa"], "operator": "<"},
            "Iniciar acompanhamento pedagógico preventivo")
    if presenca < THRESHOLDS["presenca_critica"]:
        add("frequencia_critica", "Presença em faixa crítica", 10,
            {"field": "presenca_percentual", "observed": presenca, "threshold": THRESHOLDS["presenca_critica"], "operator": "<"},
            "Verificar faltas e risco de dependência")
    elif presenca < THRESHOLDS["presenca_baixa"]:
        add("frequencia_baixa", "Presença abaixo da faixa de alerta", 4,
            {"field": "presenca_percentual", "observed": presenca, "threshold": THRESHOLDS["presenca_baixa"], "operator": "<"})
    if reprovacoes >= 2:
        add("multiplas_reprovacoes", "Duas ou mais reprovações", 6,
            {"field": "reprovacoes", "observed": reprovacoes, "threshold": 2, "operator": ">="},
            "Criar plano de estudos e acompanhar dependências")
    if combo:
        add("combo_financeiro_engajamento", "Atraso financeiro grave combinado com desengajamento", 10,
            {"fields": ["dias_atraso_boleto", "dias_sem_login"], "observed": {"dias_atraso_boleto": atraso, "dias_sem_login": login}, "thresholds": {"dias_atraso_boleto": 15, "dias_sem_login": 14}},
            "Priorizar análise pela coordenação")
    if early and (atraso > 15 or login > 14 or nota < 6):
        add("risco_inicio_curso", "Sinal de risco no início do curso", 6,
            {"field": "semestre", "observed": features["semestre"], "condition": "semestre <= 2 e pelo menos um sinal de risco"},
            "Avaliar intervenção precoce no 1º ou 2º semestre")

    adjusted = min(100.0, max(0.0, model_score + boost))
    critical_flags = [f for f in flags if "critico" in f or "abandono" in f or "combo" in f]
    if adjusted >= 70 or len(critical_flags) >= 2:
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

    unique_actions = list(dict.fromkeys(actions))
    if not unique_actions and level == "baixo":
        unique_actions.append("Monitoramento rotineiro")
    return {
        "adjusted_score": round(adjusted, 1),
        "model_score": round(model_score, 1),
        "risk_level": level,
        "rule_flags": flags,
        "rule_boost": round(boost, 1),
        "rule_adjustments": adjustments,
        "recommended_actions": unique_actions[:5],
        # Compatibilidade: confiança é apenas concordância heurística entre faixas,
        # não probabilidade calibrada nem medida estatística de certeza.
        "confidence": confidence,
        "confidence_basis": "heuristic_model_rule_band_agreement",
    }
