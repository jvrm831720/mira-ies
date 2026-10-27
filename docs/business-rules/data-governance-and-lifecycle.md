# Governança e ciclo de vida de dados e modelos

## Modalidades de treinamento

### Modos presentes no código
- `shared_training`: política que pode autorizar contribuição elegível para treinamento compartilhado da base global.
- `institution_only`: bloqueia contribuição para treino compartilhado; pode permitir treinamento institucional apenas com autorização separada e elegibilidade independente.
- `evaluation`: finalidade reconhecida pelo serviço de política, mas seu contrato de negócio e usos concretos precisam de revisão.

### Evidências principais
- `backend/app/models/data_governance.py`: `TenantDataUsePolicy`, referência/versão contratual, vigência, expiração, revogação, aprovador e evidência.
- `backend/app/models/institutional_training_authorization.py`: autorização local separada, evidência, elegibilidade e vigência.
- `backend/app/services/training_policy.py`: nega treinamento compartilhado se não houver política efetiva, vigente, não revogada, aprovada e evidenciada; exige elegibilidade do dataset. A autorização local é checada separadamente.
- `backend/app/services/shared_training_guard.py` e `shared_training_dataset.py`: guardas e construção de dataset devem ser revisados fluxo a fluxo para comprovar aplicação universal.
- `backend/app/models/tenant.py`: artefatos e eventos de treinamento carregam tenant, escopo, versão e snapshots.
- `backend/tests/test_training_policy.py`, `test_shared_training_guard.py`, `test_shared_training_dataset.py`, `test_institutional_training_authorization.py`, `test_model_lifecycle.py`, `test_governance_e2e.py`.

## Regras

**RB-GOV-001 — Fail closed no treino compartilhado**
- Decisão: APROVADA. Implementação: PARCIALMENTE IMPLEMENTADA (serviço de política existe; auditoria persistente por decisão no pipeline não foi comprovada). Validação: TESTADA PARCIALMENTE.
- Deve negar contribuição sem política atual aprovada, evidência contratual, vigência válida e dataset elegível.
- Ator: pipeline de treinamento; dados: tenant, policy_id, finalidade, elegibilidade e referência de evidência.
- Aceite: ausência, revogação, expiração, modo institucional ou dataset inelegível sempre negam o treino global.
- Risco: P0 — compartilhamento sem autorização.
- Dependências: RB-SEC-001, RB-AUD-001. Pendência: persistir decisão e proveniência do conjunto em trilha auditável.

**RB-GOV-002 — Treino institucional com autorização independente**
- Decisão: APROVADA. Implementação: IMPLEMENTADA — EVIDÊNCIA ENCONTRADA no resolver de autorização; validação parcial.
- Deve exigir autorização local efetiva, não revogada, não expirada, aprovada por admin e com evidência contratual e referência de elegibilidade.
- Aceite: autorização compartilhada não substitui autorização institucional; falta de qualquer evidência bloqueia.
- Risco: P0. Pendência: comprovar que todos os caminhos de treino local chamam o resolver.

**RB-GOV-003 — Rastreabilidade de modelo usado em previsão**
- Decisão: APROVADA. Implementação: PARCIALMENTE IMPLEMENTADA. Validação: TESTADA PARCIALMENTE no E2E da PR #47.
- Previsão deve registrar/expor escopo e versão exata do modelo.
- Evidência: `backend/app/api/scoring.py`, `TrainingEvent.model_version/model_scope`, testes `test_governance_e2e.py`.
- Aceite: previsão sem versão não retorna sucesso; cada resultado pode ser ligado a versão/escopo.
- Pendência: validar todos os caminhos de scoring e persistência em staging.

**RB-GOV-004 — Mudança de compartilhado para institucional**
- Decisão: PENDENTE para tratamento de modelos já treinados; implementação parcial (a política bloqueia futuras contribuições, mas revisão de jobs pendentes não comprovada).
- A partir da vigência efetiva, bloquear novas contribuições globais e reavaliar runs pendentes antes de consumir seus dados.
- Não afirmar que retirar linhas futuras apaga influência já aprendida pelo modelo.
- Aceite proposto: inventariar datasets/runs/modelos afetados e suspender decisões de publicação até decisão formal.
- Risco: P0. Ação requerida: aprovação de política jurídica/técnica para rollback, retreino, unlearning ou outra medida.

## Ciclo de vida de modelo

O esquema possui `candidate`, `approved`, `active`, `rejected`, `retired` como estados previstos pelo ciclo de vida; o estado efetivo e transições devem ser confirmados em `backend/app/api/outcomes.py` e testes. Ativação deve ser auditada e não deve deixar múltiplos modelos ativos no mesmo escopo sem contrato explícito. Rollback deve referenciar o artefato restaurado e manter histórico.

## Privacidade e exclusão

Não foi encontrada nesta fase uma política completa de retenção e descarte para dados brutos, snapshots de features, logs, backups e influência de modelos. Não inventar prazos legais. Necessário mapear os dados e solicitar revisão contratual/jurídica apropriada.
