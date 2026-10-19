# Motor Preditivo de Risco — Documentação Técnica

## Visão Geral

O motor calcula um **Risk Score de 0 a 100** para cada aluno e explica os **Top 3 fatores** que mais influenciam o risco, usando **XGBoost + SHAP**.

### Níveis de risco

| Score   | Nível    | Ação sugerida                          |
|---------|----------|----------------------------------------|
| 0–39    | Baixo    | Monitoramento rotineiro                |
| 40–69   | Médio    | Acompanhamento preventivo              |
| 70–100  | Crítico  | Intervenção prioritária (fila humana)  |

---

## Features utilizadas (12)

### Originais (da planilha)
- `dias_atraso_boleto`
- `recorrencia_atrasos`
- `dias_sem_login`
- `presenca_percentual`
- `nota_media`
- `reprovacoes`
- `semestre`

### Derivadas (feature engineering)
- `is_early_semester` → 1 se semestre ≤ 2
- `atraso_grave` → 1 se atraso > 15 dias
- `engajamento_critico` → 1 se dias sem login > 14
- `desempenho_baixo` → 1 se nota média < 6.0
- `presenca_baixa` → 1 se presença < 70%

---

## Treinamento

No MVP o modelo é treinado com **dados sintéticos realistas**.

- Algoritmo: `XGBClassifier`
- Métrica principal: ROC-AUC
- Artefatos: `backend/models/trained/`

O modelo é carregado (ou treinado) automaticamente no startup da API.

```
POST /api/v1/model/train?n_samples=4000
```

---

## Explicabilidade (SHAP)

Top 3 fatores no formato:

```json
{
  "feature": "dias_atraso_boleto",
  "label": "Dias de atraso no boleto",
  "value": 18.0,
  "shap_value": 0.42,
  "contribution": "aumenta_risco",
  "impact_pct": 35.2
}
```

Resumo humano:
> "1º Atraso de 18 dias no boleto + 2º 20 dias sem acesso ao AVA + 3º Nota média 4.5"

---

## Fluxo recomendado

1. Upload → `POST /api/v1/upload`
2. Resumo → `GET /api/v1/risk/summary`
3. Críticos → `GET /api/v1/risk/critical`
4. Ficha → `GET /api/v1/students/{id}/risk`
