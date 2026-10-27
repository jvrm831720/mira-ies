# DOM-08 — Casos e Central de trabalho

## RB-OPS-001 — Aluno e caso operacional são conceitos distintos
- Decisão PENDENTE; implementação NÃO VERIFICADA; validação NÃO TESTADA.
- Norma proposta: cadastro representa aluno; caso representa trabalho com responsável, prioridade, prazo, tentativas, resolução e reabertura. Não assumir que logs ou lista de alunos constituem uma máquina de casos completa.
- Aceite: tarefa tem ID, responsável, estado e histórico independentes; duplicidade e concorrência são testadas.
- Evidência inicial: frontend/src/app/(app)/trabalho/page.tsx, backend/app/models/intervention.py; não prova ciclo completo. Risco P2.

## RB-OPS-002 — Prioridade considera risco e possibilidade de ação
- Decisão RECOMENDAÇÃO; implementação NÃO VERIFICADA; validação NÃO TESTADA.
- Norma proposta: priorização considera risco, urgência, evidência e possibilidade de intervenção; score sozinho não substitui regra de fila.
- Aceite: ordem determinística, motivo visível, desempate estável; opt-out/sem contato não cria envio inviável.
- Evidência inicial: frontend/src/components/risk/critical-list.tsx, backend/app/agents/rules.py. Pendente: definir ciclo de vida, SLA e métricas de resolução.
