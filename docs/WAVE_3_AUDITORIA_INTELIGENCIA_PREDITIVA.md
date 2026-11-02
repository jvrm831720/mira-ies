# Wave 3 — Auditoria inicial de inteligência preditiva e confiabilidade dos dados

Data da auditoria: 2026-11-02  
Base auditada: `main` no commit `611a4dde3ef2cb50630045df421afbb11ca3be0e`  
Branch de trabalho: `feat/wave-3-predictive-data-reliability`

## Resumo executivo

A MIRA já possui componentes importantes: modelo XGBoost, calibração isotônica, regras de negócio, snapshots de features, histórico versionado de avaliações, seis sinais e sete grupos virtuais. Os testes puros dos sinais e grupos cobrem casos de ausência de dados e estados indeterminados.

Isso ainda não comprova confiabilidade preditiva em operação. O modelo-base é treinado com dados sintéticos derivados de regras artificiais. O próprio metadado do treinamento declara que as métricas não representam validação em dados reais de uma IES. Além disso, a engenharia de features converte campos ausentes em valores favoráveis antes do scoring.

## Achados confirmados

### P0 — Ausência de dados convertida em evidência favorável

Arquivo: `backend/app/ml/features.py`

- `dias_sem_login` ausente vira `0`.
- `presenca_percentual` ausente vira `100.0`.
- `nota_media` ausente vira `7.0`.
- `dias_atraso_boleto`, recorrência e reprovações ausentes viram `0`.
- `semestre` ausente vira `3`.
- `missing_feature_flags()` identifica apenas parte dos campos ausentes, mas isso não impede a geração do score nem altera as features enviadas ao modelo.
- `features_to_dataframe()` preenche colunas ausentes com zero.

Impacto: o modelo e as regras podem tratar falta de informação como ausência de risco. O score pode parecer válido mesmo quando a cobertura acadêmica, financeira ou comportamental é insuficiente.

O mesmo padrão aparece no contrato ad hoc `StudentFeaturesInput` em `backend/app/api/scoring.py`, cujos campos têm defaults como 0, 100% de presença e nota 7. Uma requisição parcial pode, portanto, parecer um perfil completo.

### P0 — Métricas do modelo-base não validam desempenho real

Arquivo: `backend/app/ml/model.py`

- `_generate_synthetic_training_data()` cria exemplos a partir de perfis e de uma fórmula de risco definida no próprio código.
- `train_model()` treina e calibra XGBoost com esse conjunto sintético.
- O holdout é separado em treino, calibração e teste, mas todos os subconjuntos derivam da mesma distribuição sintética e da mesma regra geradora.
- AUC, average precision, Brier, precision, recall e matriz de confusão são calculados, mas não medem generalização para uma IES real.
- O metadado inclui um disclaimer explícito de que as métricas sintéticas não representam validação em dados reais.

Conclusão: essas métricas podem testar consistência técnica do pipeline, mas não devem ser apresentadas como acurácia real ou evidência de capacidade de prever evasão.

### P1 — Regras de negócio também consomem defaults

Arquivo: `backend/app/ml/rules.py`

A camada de regras usa defaults como atraso/login/reprovações = 0, presença = 100 e nota = 7 quando uma feature não existe. Isso reforça o problema de ausência de dados e pode reduzir o score ajustado ou deixar de ativar alertas.

Os limiares e boosts estão explícitos no código, mas ainda precisam de documentação como regras operacionais configuradas, separadas de pesos aprendidos pelo modelo e sem alegação de validação estatística.

### P1 — Explicabilidade não é garantida em toda avaliação

Arquivos: `backend/app/ml/scoring.py`, `backend/app/ml/explain.py`

- SHAP em lote é opcional e, por padrão, pode ficar desligado.
- Quando não executado, o histórico registra explicação indisponível; isso é preferível a inventar fatores, mas a interface deve deixar essa limitação visível.
- O cálculo SHAP apresentado usa o modelo-base carregado por `load_model()`; o scoring pode resolver um modelo institucional diferente via `resolve_scoring_model()`. Isso exige auditoria específica para impedir que explicações do modelo-base sejam confundidas com explicações do modelo que realmente gerou a avaliação.
- A lista de top fatores não substitui a exposição de origem, cobertura, atualidade e limitações dos dados usados.

### P1 — Proveniência e atualidade por variável ainda não estão demonstradas

O modelo `Student` contém os valores atuais e `raw_data`, enquanto o histórico guarda `features_snapshot` e contexto do lote. Na estrutura auditada não há evidência suficiente de proveniência temporal individual por campo (origem, instante de extração, período de referência e validade). O lote tem `uploaded_at` e `processed_at`, mas isso não prova quando o dado acadêmico, financeiro ou comportamental foi efetivamente atualizado na origem.

### P2 — Sinais e grupos já têm uma base semântica consistente

Arquivos: `backend/app/signals/catalog.py`, `backend/app/signals/evaluate.py`, `backend/app/student_groups/catalog.py`, `backend/app/student_groups/evaluate.py`

- Há exatamente seis sinais versionados e sete grupos virtuais.
- Sinais tratam NULL/ausente como `insufficient_data`, exceto o meta-sinal `missing_score`.
- Os grupos reutilizam o resultado dos sinais, com estados `TRUE`, `FALSE` e `INDETERMINATE`.
- O grupo de múltiplos sinais exclui `missing_score` e não conta sinais indeterminados como ativos.
- Há testes puros para ausência, valores inválidos, histórico insuficiente, incompatibilidade de versões e combinações de sinais.

Ponto de atenção: o avaliador de sinais recebe o snapshot do aluno e não as features efetivamente consumidas pelo modelo. Hoje, portanto, um sinal pode indicar dado insuficiente enquanto o score armazenado foi calculado usando um default favorável. A semântica precisa ser unificada.

### P2 — Histórico e versionamento já existem, mas não provam qualidade do score

Arquivos: `backend/app/models/risk_assessment.py`, migrations `018`–`020`, `backend/app/api/risk_history_impl.py`, `docs/risk-monitoring-history.md`

As avaliações persistem score, nível, versão do modelo, versão da semântica, escopo, snapshot de features, explicação e contexto. Comparações entre versões diferentes são bloqueadas. Isso fornece uma base adequada para auditoria longitudinal, mas a confiabilidade depende da qualidade dos dados e do modelo que gerou cada avaliação.

## Inventário do que existe

| Área | Estado observado |
|---|---|
| Modelo-base XGBoost | Implementado; treinamento sintético |
| Calibração isotônica | Implementada; não validada em dados reais |
| Métricas técnicas | AUC, AP, Brier, precision, recall, F1, accuracy e matriz de confusão no treino sintético |
| Regras e limiares | Implementados em `rules.py`; precisam de documentação operacional |
| Features | 17 features; defaults de ausência precisam ser removidos |
| SHAP | Implementado; opcional em lote; precisa respeitar o modelo efetivamente usado |
| Histórico/versionamento | Implementado nas migrations 018–020 |
| Seis sinais | Implementados e com testes puros |
| Sete grupos | Implementados e com testes puros |
| Proveniência por campo | Não demonstrada na estrutura atual |
| Validação real em IES | Não comprovada nesta auditoria |

## Plano recomendado de execução

### Wave 3.1 — Integridade e cobertura de dados (bloqueador)

1. Criar representação explícita de valor ausente, inválido, desatualizado e não aplicável.
2. Remover defaults favoráveis do caminho de scoring e do contrato de previsão ad hoc.
3. Não emitir score preditivo utilizável quando os requisitos mínimos de cobertura não forem atendidos; retornar estado indeterminado e motivos verificáveis.
4. Separar score do modelo, ajustes de regras e estado de confiabilidade/cobertura.
5. Preservar no snapshot os valores observados, indicadores de ausência e metadados de origem/atualidade.
6. Garantir que regras de negócio não substituam ausência por zero ou valores favoráveis.
7. Testar importação parcial, campos inválidos, dados desatualizados e combinações de cobertura.

### Wave 3.2 — Contrato do modelo e explicabilidade

1. Publicar catálogo das 17 features: descrição, tipo, fonte, transformação, unidade, janela temporal, validação e tratamento de ausência.
2. Documentar hiperparâmetros, pesos/importance, regras, boosts, limiares e classificação, sem misturar importância do XGBoost com causalidade.
3. Fazer SHAP usar o mesmo artefato/modelo e versão que gerou o score.
4. Exibir fatores que aumentam e reduzem risco, evidência observada, fonte e data de referência.
5. Exibir explicitamente quando a explicação não estiver disponível.

### Wave 3.3 — Validação estatística real

1. Preparar dataset rotulado com desfecho e janela temporal definidos.
2. Separar treino, calibração e teste temporalmente, por aluno, sem vazamento.
3. Medir precision, recall, F1, falsos positivos, falsos negativos, PR-AUC, ROC-AUC e Brier.
4. Avaliar calibração por faixas (reliability curve / expected calibration error) e tamanho de amostra por faixa.
5. Avaliar desempenho por curso/campus/modalidade quando o volume permitir.
6. Não promover modelo nem chamar score de probabilidade calibrada sem critérios mínimos de evidência e aprovação.

### Wave 3.4 — Sinais, grupos e consistência

1. Unificar semântica de cobertura do scoring, sinais e grupos.
2. Verificar os seis sinais e sete grupos com testes de contrato e cenários combinatórios.
3. Confirmar que sinal e grupo não declaram FALSE quando a fonte é insuficiente/desatualizada.
4. Validar consistência de versão, timestamp, origem e evidências.
5. Manter `missing_score` como lacuna de cobertura, nunca como grupo de baixo risco.

### Wave 3.5 — Histórico, monitoramento e governança

1. Versionar feature schema, regra, score semantics e modelo.
2. Preservar proveniência e cobertura em cada avaliação histórica.
3. Medir drift de dados e desempenho após maturação dos desfechos.
4. Criar gates para aprovação, ativação e rollback de modelos.
5. Documentar limitações e critérios de uso operacional.

## Critérios de aceite globais

- Nenhum campo ausente é convertido silenciosamente em condição favorável.
- Nenhum score é apresentado como confiável sem cobertura mínima verificável.
- Cada avaliação permite reconstruir versão, features, origem e atualização dos dados.
- Explicações correspondem ao modelo que gerou a avaliação.
- Métricas de validação são calculadas em desfechos reais, com teste temporal independente.
- Sinais e grupos mantêm estados indeterminados quando a evidência não é suficiente.
- Nenhuma métrica sintética é apresentada como desempenho real de evasão.
- Nenhuma alteração em produção ou ativação de novo modelo ocorre sem validação e autorização próprias.
