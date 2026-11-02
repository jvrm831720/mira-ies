# Wave 3.2 — Contrato do modelo e explicabilidade

**Status:** contrato técnico documentado; ver PR para implementação e testes.  
**Versão do schema de features:** `student-risk-features-v2`.  
**Versão semântica do score:** `risk-score-v1`.

## Escopo e limites

O pipeline combina um estimador XGBoost, calibrador de probabilidade (quando disponível), regras de negócio e ajuste dinâmico operacional. O score final é uma composição operacional de risco, não uma probabilidade calibrada de evasão.

O modelo base atual foi treinado com dados sintéticos gerados por uma regra heurística. As métricas desse conjunto não comprovam desempenho em uma IES real. Não interpretar o score como probabilidade validada de evasão.

## Contrato das 17 features

As sete primeiras são campos de origem. As demais são derivadas deterministicamente.

| Feature | Origem / transformação | Interpretação |
|---|---|---|
| `dias_atraso_boleto` | Origem: dias de atraso; inteiro 0–3650 | Atraso financeiro observado |
| `recorrencia_atrasos` | Origem: contagem; inteiro 0–100 | Recorrência financeira observada |
| `dias_sem_login` | Origem: dias desde último acesso; inteiro 0–3650 | Inatividade no AVA/LMS |
| `presenca_percentual` | Origem: percentual 0–100 | Presença observada |
| `nota_media` | Origem: nota 0–10 | Desempenho acadêmico observado |
| `reprovacoes` | Origem: contagem 0–100 | Reprovações observadas |
| `semestre` | Origem: semestre 1–30 | Etapa atual do curso |
| `is_early_semester` | 1 se semestre <= 2; senão 0 | Indicador derivado de início do curso |
| `atraso_grave` | 1 se dias_atraso_boleto > 15 | Indicador derivado |
| `engajamento_critico` | 1 se dias_sem_login > 14 | Indicador derivado |
| `desempenho_baixo` | 1 se nota_media < 6 | Indicador derivado |
| `presenca_baixa` | 1 se presenca_percentual < 70 | Indicador derivado |
| `risco_financeiro` | min(1, (atraso/60) * (1 + recorrencia/3) / 2) | Índice derivado, 0–1 |
| `risco_engajamento` | min(1, (dias_sem_login/45) * (1 - presença/100) * 2) | Índice derivado, 0–1 |
| `risco_academico` | min(1, ((10 - nota)/10) * (1 + reprovações/2) / 2) | Índice derivado, 0–1 |
| `combo_critico` | 1 se atraso > 15 e dias_sem_login > 14 | Interação financeira + engajamento |
| `pressao_inicial` | início do curso * max(atraso_grave, engajamento_critico, desempenho_baixo) | Interação de início de curso |

### Regras de qualidade

Todos os sete campos de origem são obrigatórios e precisam ser válidos. Ausência, valor não numérico, não finito ou fora do intervalo bloqueia o score. Zero é valor válido quando dentro do intervalo. Não imputar dados ausentes como condição favorável.

## Estimador, calibração e versão

- Estimador: XGBoost binário.
- Calibração: isotônica quando o artefato de calibrador está disponível e é compatível.
- Score do modelo: probabilidade retornada pelo estimador/calibrador multiplicada por 100.
- O estimador usado no SHAP deve ser exatamente o objeto usado na previsão daquela execução, incluindo o escopo institucional quando ativo.
- A versão e o escopo do modelo devem acompanhar a explicação.
- SHAP explica a saída bruta do estimador. A calibração posterior, regras de negócio e ajuste dinâmico não são contribuições SHAP. A API deve identificá-las separadamente.
- Se SHAP não for calculado, a resposta deve dizer isso. Não criar fatores substitutos nem zerar contribuições silenciosamente.

## Regras de negócio e ajustes

| Condição | Delta |
|---|---:|
| Atraso >= 30 dias | +15 |
| Atraso >= 15 dias e < 30 | +8 |
| Recorrência >= 3 | +5 |
| Dias sem login >= 21 | +12 |
| Dias sem login >= 14 e < 21 | +5 |
| Nota < 4 | +12 |
| Nota < 6 e >= 4 | +5 |
| Presença < 50% | +10 |
| Presença < 70% e >= 50% | +4 |
| Reprovações >= 2 | +6 |
| Atraso > 15 e dias sem login > 14 | +10 |
| Semestre <= 2 e pelo menos um sinal (atraso > 15, login > 14, nota < 6) | +6 |

Os deltas são aditivos e o score ajustado pelas regras é limitado ao intervalo 0–100. A resposta deve registrar cada regra aplicada, evidência observada, limite e delta. Recomendações são sugestões operacionais, não evidências.

## Composição do score final

1. `model_score`: probabilidade do modelo/calibrador * 100.
2. `business_rule_adjustment`: soma dos deltas das regras, com limite aplicado ao score ajustado.
3. `dynamic_adjustment`: ajuste operacional já existente.
4. `final_score`: score exibido após os ajustes, limitado a 0–100.

Faixas: baixo < 40; médio >= 40 e < 70; crítico >= 70. A regra de classificação por combinação de sinais críticos também pode elevar a faixa para crítico. O campo legado `confidence` representa concordância heurística entre faixas do modelo e das regras; não é probabilidade, intervalo de confiança ou calibração estatística.

## Semântica para a operação

- **Evidência observada:** valor do campo de origem, com unidade e período quando disponível.
- **Fator do modelo:** contribuição SHAP para a saída bruta do estimador; sinal positivo aumenta essa saída, negativo reduz. `impact_pct` é participação na magnitude SHAP do caso, não percentual do score.
- **Ajuste de regra:** condição determinística com evidência, limiar e pontos adicionados.
- **Ajuste dinâmico:** alteração operacional separada, com origem rastreável.
- **Recomendação:** próxima ação sugerida; nunca deve ser exibida como se fosse uma causa observada.

## Pendências fora desta wave

- Calibração e validação em coortes reais, com rótulos de evasão e horizonte definido.
- Métricas por curso, modalidade e período, com análise de viés e estabilidade.
- Proveniência e frescor por campo de origem.
- Explicação SHAP do pipeline calibrado completo (se houver método tecnicamente apropriado); nesta wave, a saída explicada é explicitamente a do estimador bruto.

## Parâmetros e geração do modelo base atual

O estimador base é um `XGBClassifier` com: `n_estimators=200`, `max_depth=5`, `learning_rate=0.06`, `subsample=0.85`, `colsample_bytree=0.8`, `reg_lambda=1.2`, `reg_alpha=0.3`, `min_child_weight=4`, `gamma=0.1`, objetivo `binary:logistic` e `random_state=42` no treino padrão.

O conjunto sintético é construído a partir de três perfis (baixo, médio e alto) e recebe rótulo por uma função logística heurística. Os coeficientes da função sintética são: atraso financeiro 0,30; recorrência 0,15; dias sem login 0,22; ausência de presença 0,12; nota baixa 0,18; reprovações 0,12; início de semestre 0,10; atraso grave 0,12; engajamento crítico 0,12; combo crítico 0,10; risco financeiro 0,08; risco de engajamento 0,08; risco acadêmico 0,08. Ruído normal com desvio 0,07 é adicionado antes da função logística; rótulo positivo quando a probabilidade sintética excede 0,42.

Esses coeficientes definem a geração dos rótulos sintéticos. **Não são pesos do XGBoost**, nem efeitos causais, nem estimativas de impacto sobre evasão real. A importância do XGBoost é calculada separadamente pelo estimador treinado.
