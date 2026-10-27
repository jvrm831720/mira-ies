# DOM-10 — Resultados, métricas e analytics

## RB-ANA-001 — KPI reproduzível com denominador explícito
- Decisão RECOMENDAÇÃO; implementação PARCIALMENTE IMPLEMENTADA; validação NÃO TESTADA.
- Norma proposta: todo KPI informa definição, fórmula, unidade, período, filtros, denominador, fonte, atualização e limitações.
- Ator/dados: gestão/analytics; InterventionLog, ProviderCallMetric, agregados e outcome.
- Aceite: o mesmo filtro e snapshot reproduzem resultado; enviados, entregues, lidos, respondidos e retidos são métricas distintas.
- Evidência: backend/app/models/intervention.py contém eventos e agregados; docs/RETENTION_EVENTS.md descreve eventos. Catálogo completo de fórmulas ainda não foi localizado.
- Risco P1; decidir modelo de atribuição e regras de coorte. Nenhuma afirmação causal sem método adequado.

## RB-ANA-002 — Outcome observado não prova causalidade
- Decisão APROVADA (princípio do prompt fundador); implementação PARCIALMENTE IMPLEMENTADA; validação NÃO TESTADA.
- Norma: relatar associação observada entre intervenção e retenção, sem afirmar que a intervenção causou o resultado sem desenho causal apropriado.
- Aceite: dashboards incluem janela, fonte e limitações; ausências e atraso de atualização são expostos.
- Evidência: backend/app/models/intervention.py, docs/RETENTION_EVENTS.md. Pendente: metodologia formal de atribuição e reprodutibilidade histórica.
