# DOM-02 — Instituições e isolamento

## RB-SEC-001 — Escopo institucional no servidor
- Decisão: APROVADA. Implementação: PARCIALMENTE IMPLEMENTADA. Validação: TESTADA PARCIALMENTE.
- Norma: cada instituição acessa apenas seus alunos, lotes, campanhas, intervenções, jobs e outcomes. Backend resolve tenant a partir da identidade autenticada; não confia somente no tenant_id enviado pelo cliente.
- Fluxo: autenticar → resolver tenant → validar escopo do recurso → operar. Recurso alheio é negado sem revelar sua existência.
- Aceite: credencial A com IDs de B não lê nem altera dados em URL, corpo, query, exportação ou job.
- Evidência: backend/app/models/tenant.py, backend/app/models/student.py, backend/app/services/tenant.py; testes de isolamento de campanhas e test_governance_e2e.py.
- Dependência: RB-AUT-001 e RB-RBAC-001. Risco P0; falta cobertura completa endpoint por endpoint.

## RB-SEC-002 — Instituição inativa
- Decisão: APROVADA em docs de segurança. Implementação: NÃO VERIFICADA em todos os caminhos. Validação: TESTADA PARCIALMENTE.
- Norma: tenant inativo não inicia operações comuns; jobs pendentes e webhooks devem revalidar status.
- Evidência: backend/app/models/tenant.py, docs/CONTROL_CENTER_SECURITY_REVIEW.md. Risco P0; testar tokens legados e callbacks.

## RB-SEC-003 — Encerramento e exclusão
- Decisão: RECOMENDAÇÃO. Implementação: NÃO VERIFICADA. Validação: NÃO TESTADA.
- Norma proposta: preferir desativação; exclusão física exige inventário de dependências, política de retenção aprovada e auditoria.
- Evidência: modelos com ondelete; docs/MIRA_CONTROL_CENTER.md. Risco P0/P1; prazos e procedimento jurídico pendentes.



## Expansão da auditoria — API de risco e escopo de lote (2026-10-27)

### RB-SEC-004 — Endpoints de risco não revelam aluno/lote de outro tenant
- **Decisão:** APROVADA (regra de isolamento existente). **Implementação:** EVIDÊNCIA ENCONTRADA no escopo verificado. **Validação:** nova regressão adicionada e aprovada pelo CI GitHub Actions run #331 (commit 34388663091e8701f05ee776326ab20fe51bbf8b).
- **Regra:** leitura do risco por ID, resumo por lote, lista de críticos por lote e scoring de lote devem sempre limitar dados ao tenant autenticado. ID de recurso de outro tenant não deve revelar nem alterar o recurso.
- **Critérios de aceite:** tenant B recebe 404 ao consultar risco de aluno de A; resumo/lista para batch de A não expõe linhas a B; tentativa de scoring do batch alheio é negada.
- **Evidência:** backend/app/api/scoring.py; filtros por `Student.tenant_id == auth.tenant_id` em resumo, críticos e risco individual; serviço `score_batch` recebe `tenant_id` do contexto autenticado.
- **Teste novo:** `backend/tests/test_governance_audit_edges.py::test_risk_endpoints_do_not_disclose_another_tenants_student_or_batch`. O run #331 terminou com sucesso.
- **Limite:** cobre endpoints de risco e scoring de lote identificados, não todos os endpoints/exports/jobs/conectores. Risco P0 até concluir inventário integral.


## Fase 3 — limites da evidência de isolamento (2026-10-27)

A inspeção de `backend/app/main.py` confirma que a API registra routers de upload, scoring, conectores, outcomes, agentes, campanhas e execução de campanhas, webhooks de entrega, autenticação, organização, faturamento e administração interna. Esse registro é um índice inicial de superfície, não uma validação de isolamento por rota.

- **Evidência positiva limitada:** os endpoints selecionados em `backend/app/api/scoring.py` filtram alunos por `auth.tenant_id`, e o scoring de lote recebe tenant autenticado.
- **Lacuna P0:** ainda é necessário inspecionar cada rota e serviço dos routers registrados, inclusive IDs fornecidos pelo cliente, filtros opcionais, exports, consultas agregadas, reprocessamento e acesso a recursos por URL.
- **Lacuna de assíncronos:** filas, workers, callbacks e webhooks devem preservar tenant_id desde o enqueue até a leitura, efeito externo, retry e consulta de status; a lista de routers não demonstra esse ciclo completo.
- **Estado:** inventário iniciado, não concluído. Não declarar isolamento multi-tenant integralmente validado.
