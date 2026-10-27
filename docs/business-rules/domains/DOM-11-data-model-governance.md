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
