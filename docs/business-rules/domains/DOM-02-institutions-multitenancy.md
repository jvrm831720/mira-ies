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
