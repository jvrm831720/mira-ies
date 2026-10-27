# DOM-15 — Observabilidade, confiabilidade e continuidade

## RB-REL-001 — Retry limitado e dead-letter
- Decisão APROVADA; implementação IMPLEMENTADA — EVIDÊNCIA ENCONTRADA; validação TESTADA PARCIALMENTE.
- Norma: jobs assíncronos devem ter idempotência, backoff e limite de tentativas; esgotamento vai para dead-letter e não pode ser consultado por outro tenant.
- Evidência: backend/app/services/retention_queue.py, backend/app/worker.py, docs/AGENTES.md, backend/tests/test_retention_queue_reliability.py.
- Aceite: repetição retorna mesmo job, retries vencem em ordem, dead-letter preserva tenant, logs minimizam payload. Risco P1.

## RB-REL-002 — Timeout externo é resultado desconhecido até reconciliação
- Decisão APROVADA em docs de agentes; implementação PARCIALMENTE IMPLEMENTADA; validação TESTADA PARCIALMENTE.
- Norma: timeout/erro de transporte não permite assumir que mensagem não foi enviada; marcar unknown e reconciliar, evitando fallback que duplique contato.
- Evidência: backend/app/agents/orchestrator.py, backend/app/models/intervention.py, docs/AGENTES.md. Risco P1; caos/rede real pendente.

## RB-REL-003 — Recuperação operacional testada
- Decisão RECOMENDAÇÃO; implementação NÃO VERIFICADA; validação NÃO TESTADA.
- Norma proposta: releases com migrações precisam de backup/restore e plano de rollback testado em staging; não usar downgrade destrutivo sem recuperação comprovada.
- Evidência: docs/CONTROL_CENTER_SECURITY_REVIEW.md. Pendente: evidência de restore real.
