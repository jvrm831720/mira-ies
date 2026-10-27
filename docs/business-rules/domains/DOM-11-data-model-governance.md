# DOM-11 — Governança de dados e modelos

Ver [governança e ciclo de vida](../data-governance-and-lifecycle.md) para regras e dependências.

## RB-GOV-001 — Treinamento compartilhado fail-closed
- Decisão APROVADA; implementação PARCIALMENTE IMPLEMENTADA; validação TESTADA PARCIALMENTE.
- Norma: treino global exige política efetiva, vigente, não revogada, aprovada, com evidência contratual e dataset elegível.
- Evidência: backend/app/models/data_governance.py, backend/app/services/training_policy.py, backend/app/services/shared_training_guard.py, backend/tests/test_training_policy.py e test_shared_training_guard.py.
- Aceite: falta, expiração, revogação, modo institution_only ou dataset inelegível bloqueiam. Risco P0; persistência da decisão no pipeline ainda pendente.

## RB-GOV-002 — Treinamento institucional exige autorização separada
- Decisão APROVADA; implementação IMPLEMENTADA — EVIDÊNCIA ENCONTRADA no resolver; validação TESTADA PARCIALMENTE.
- Norma: autorização institucional própria, evidência contratual, aprovador e elegibilidade são independentes da autorização de compartilhamento.
- Evidência: backend/app/models/institutional_training_authorization.py e training_policy.py; teste test_institutional_training_authorization.py.
- Pendência: comprovar todos os caminhos de treino local.

## RB-GOV-003 — Predição identifica versão exata
- Decisão APROVADA; implementação PARCIALMENTE IMPLEMENTADA; validação TESTADA PARCIALMENTE no E2E PR #47.
- Norma: resposta e histórico devem indicar escopo e versão exata; sem versão, falhar de forma segura.
- Evidência: backend/app/api/scoring.py, TrainingEvent.model_version/model_scope, backend/tests/test_governance_e2e.py.

## RB-GOV-004 — Mudança A→B revisa runs e modelos anteriores
- Decisão PENDENTE para tratamento de influência passada; implementação PARCIALMENTE IMPLEMENTADA para bloquear contribuições futuras; validação TESTADA PARCIALMENTE.
- Norma provisória: bloquear novos dados globais na vigência B e revisar runs pendentes; não alegar que excluir dados futuros apaga influência de modelo já treinado.
- Risco P0. Decisão de retreino/unlearning/rollback e tratamento contratual exige fundador e assessoria jurídica.



## Expansão da auditoria — efetividade temporal e autorização (2026-10-27)

### RB-GOV-005 — Somente a política vigente na data da decisão controla o treino
- **Decisão:** APROVADA (consistente com a política versionada). **Implementação:** EVIDÊNCIA ENCONTRADA no resolver. **Validação:** teste de regressão adicionado; GitHub Actions run #331 passou para o commit 34388663091e8701f05ee776326ab20fe51bbf8b.
- **Regra:** registros com `effective_at` futuro não substituem a política efetiva atual antes da data/hora de vigência. Após a vigência, a nova política passa a controlar novas decisões.
- **Critérios de aceite:** política compartilhada vigente permite treino compartilhado quando o dataset é elegível; política futura `institution_only` não antecipa bloqueio; depois da vigência, bloqueia.
- **Evidência:** backend/app/services/training_policy.py, filtro de registros efetivos por `effective_at <= now`.
- **Teste novo:** `backend/tests/test_governance_audit_edges.py::test_future_dated_policy_does_not_take_effect_early`. O run #331 terminou com sucesso.

### RB-GOV-006 — Autorização institucional e autorização de compartilhamento são controles distintos
- **Decisão:** APROVADA. **Implementação:** EVIDÊNCIA ENCONTRADA no resolver de autorização local e nos bloqueios do treino por tenant. **Validação:** TESTADA PARCIALMENTE nos testes existentes.
- **Regra:** uma política de compartilhamento, mesmo aprovada, não substitui a autorização independente de treino institucional; a autorização local precisa de aprovação, evidência contratual, referência de elegibilidade do dataset e vigência.
- **Evidência:** backend/app/services/training_policy.py::resolve_institutional_training_authorization; backend/app/ml/tenant_train.py; backend/tests/test_institutional_training_authorization.py.
- **Risco:** P0 se houver caminho de treino que não use o gate. Inventário de todos os callers e trilhas de treino continua pendente.

### Lacuna persistente — decisões não necessariamente auditadas por execução
O resolver retorna a decisão, tenant, finalidade, modo, ID da política e motivo, mas essa função por si só não persiste um evento de auditoria. O guard compartilhado exige aprovação para todos os tenants contribuintes antes de prosseguir, porém a cobertura de todos os chamadores e a persistência da decisão por run/dataset ainda não foram demonstradas. Não confundir retorno de decisão com trilha de auditoria durável.


## Fase 3 — inventário dirigido de caminhos de treinamento (2026-10-27)

### RB-GOV-007 — Retreinamento global legado permanece bloqueado
- **Decisão:** APROVADA como proteção temporária até haver fluxo versionado, revisável e auditável. **Implementação:** EVIDÊNCIA ENCONTRADA. **Validação:** endpoint identificado; teste específico de contrato HTTP ainda deve ser registrado ou localizado.
- **Regra:** `POST /api/v1/model/train` não pode sobrescrever o modelo global ativo pelo caminho legado.
- **Evidência:** `backend/app/api/scoring.py::retrain_model` responde HTTP 409 e informa que o treino global está bloqueado até existir relatório versionado, aprovação explícita, ativação controlada e rollback.
- **Limite:** a resposta 409 prova o bloqueio deste endpoint, não a ausência de outros caminhos de escrita/treino global.

### RB-GOV-008 — Treino institucional é autorizado antes do treinamento
- **Decisão:** APROVADA. **Implementação:** EVIDÊNCIA ENCONTRADA no caminho examinado. **Validação:** TESTADA PARCIALMENTE pelos testes de autorização existentes; falta prova E2E de todos os pontos de entrada.
- **Regra:** o treino local deve verificar autorização institucional independente antes de atualizar prontidão ou treinar, e deve selecionar eventos rotulados do tenant solicitado.
- **Evidência:** `backend/app/ml/tenant_train.py::train_tenant_model` consulta `resolve_institutional_training_authorization` antes de `refresh_tenant_readiness`, seleciona `TrainingEvent` pelo `tenant.id` e exige também decisão permitida de `resolve_training_policy` com finalidade `institutional_training`.
- **Limite:** o exame deste serviço não comprova que todas as chamadas passam por ele, nem que logs de cada decisão são persistidos por run/dataset.

### RB-GOV-009 — Guard compartilhado deve receber todos os tenants contribuintes
- **Decisão:** APROVADA. **Implementação:** EVIDÊNCIA ENCONTRADA no serviço guard. **Validação:** TESTADA PARCIALMENTE pelos testes de guard existentes.
- **Regra:** lista vazia/inválida falha fechada; uma única instituição negada bloqueia a execução compartilhada inteira, sem descartar silenciosamente apenas os registros negados.
- **Evidência:** `backend/app/services/shared_training_guard.py::require_shared_training_authorization` deduplica a lista, exige pelo menos um tenant válido e levanta `SharedTrainingBlockedError` se qualquer decisão for negada.
- **Lacuna P0:** ainda não foi demonstrado que todos os pipelines, jobs, comandos operacionais e futuras rotas chamam esse guard antes de materializar dados ou ajustar o modelo global.

### Regra de release
Não ativar treinamento compartilhado com dados reais até haver inventário de todos os pontos de entrada, prova de chamada do guard antes da leitura/materialização dos dados, trilha persistente por run/dataset e tratamento aprovado de A→B.
