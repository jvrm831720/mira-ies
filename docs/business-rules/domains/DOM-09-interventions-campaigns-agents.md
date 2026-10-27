# DOM-09 — Intervenções, campanhas, canais e agentes

## RB-INT-001 — Opt-out global bloqueia contato
- Decisão APROVADA; implementação IMPLEMENTADA — EVIDÊNCIA ENCONTRADA; validação TESTADA PARCIALMENTE.
- Norma: Student.communication_opt_out=true bloqueia qualquer canal; preferências por canal/finalidade não anulam o bloqueio global.
- Fluxo: elegibilidade → preferência → risco → anti-spam → canal → envio/dry-run → log. Sem contato viável, pular com motivo.
- Aceite: opt-out impede chamadas de provider; registrar skip sem corpo integral de mensagem.
- Evidência: backend/app/models/student.py, backend/app/services/consent.py, backend/app/agents/orchestrator.py, docs/AGENTES.md, tests test_consent_governance.py/test_agent_delivery_safety.py. Risco P0.

## RB-INT-002 — Execução, entrega e resultado são estados diferentes
- Decisão APROVADA; implementação PARCIALMENTE IMPLEMENTADA; validação TESTADA PARCIALMENTE.
- Norma: sent/submitted/delivered/read/resposta/retido não são equivalentes. Timeout ambíguo deve virar unknown e não disparar fallback imediato que possa duplicar.
- Regras documentadas: risco baixo não dispara; anti-spam default 48h por canal e 3 contatos/7 dias; dry-run é padrão; providers reais exigem configuração.
- Evidência: backend/app/models/intervention.py, backend/app/agents/orchestrator.py, backend/app/services/provider_guard.py, backend/app/services/delivery_webhooks.py, docs/AGENTES.md, docs/RETENTION_RULE_ENGINE.md.
- Aceite: replay webhook deduplicado, idempotency tenant-scoped, falha ambígua reconciliada. Risco P1; contratos reais com providers/staging pendentes.

## RB-INT-003 — Campanha versionada com no máximo uma versão ativa por tenant/slug
- Decisão APROVADA no código atual; implementação IMPLEMENTADA — EVIDÊNCIA ENCONTRADA; validação TESTADA PARCIALMENTE.
- Evidência: backend/app/models/retention_campaign.py (índice único parcial), backend/tests/test_retention_rule_engine.py e docs/RETENTION_RULE_ENGINE.md.
- Aceite: ativação de versão nova desativa a anterior; versão/ regra selecionada fica no log. Risco P1.
