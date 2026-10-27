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
