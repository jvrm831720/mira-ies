# DOM-13 — Integrações, APIs e processamento assíncrono

## RB-API-001 — Integrações respeitam tenant e validação
- Decisão APROVADA; implementação PARCIALMENTE IMPLEMENTADA; validação TESTADA PARCIALMENTE.
- Norma: credenciais e webhooks são escopados à instituição; payloads são validados; reprocessamento não deve duplicar efeitos.
- Evidência: backend/app/api/connectors.py, backend/app/services/connectors/, backend/app/api/delivery_webhooks.py, backend/app/services/delivery_webhooks.py, docs/CONECTORES.md.
- Aceite: assinatura inválida/replay é rejeitado; tenant A não atualiza B; erro de integração não confirma sucesso. Risco P0; inventário de todos os webhooks e rotação de segredos pendentes.

## RB-API-002 — Jobs têm retry limitado e consulta isolada
- Decisão APROVADA; implementação IMPLEMENTADA — EVIDÊNCIA ENCONTRADA; validação TESTADA PARCIALMENTE.
- Norma: enqueue idempotente por tenant; retry limitado com backoff; após esgotar tentativas, dead-letter e status consultável apenas pelo tenant proprietário.
- Evidência: backend/app/services/retention_queue.py, backend/app/worker.py (confirmar caminho exato), docs/AGENTES.md, backend/tests/test_retention_queue_reliability.py.
- Aceite: duplicação, backoff, dead-letter e leitura cross-tenant testados. Risco P1; crash entre chamada externa e persistência requer reconciliação.


## Fase 3 — fronteira entre rotas e execução assíncrona (2026-10-27)

O registro de routers em `backend/app/main.py` inclui conectores, outcomes, agentes, execução de campanhas de retenção e webhooks de entrega. Isso define áreas obrigatórias da auditoria, mas não comprova por si só isolamento, idempotência ou assinatura segura.

Checklist ainda pendente por endpoint/job:
- origem autenticada do tenant e autorização de papel;
- ownership dos IDs de campanha, aluno, lote, execução e callback;
- assinatura, timestamp, replay/idempotência e validação do payload do webhook;
- propagação de tenant em enqueue, retry, worker, dead-letter e consulta de status;
- comportamento diante de timeout ambíguo e reconciliação após efeito externo;
- não exposição de credenciais ou dados pessoais em logs e respostas de erro.

**Status:** os itens acima permanecem como critérios de auditoria, não como defeitos confirmados. A validação por staging/provedor real não foi executada.
