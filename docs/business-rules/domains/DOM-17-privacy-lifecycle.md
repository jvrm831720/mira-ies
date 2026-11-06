# DOM-17 — Privacidade, ciclo de vida e direitos dos titulares

## RB-PRI-001 — Minimização e retenção precisam de política explícita
- Decisão APROVADA como princípio; implementação PARCIALMENTE IMPLEMENTADA; validação NÃO TESTADA.
- Norma: coletar e expor apenas dados necessários à finalidade; definir retenção e descarte para dados brutos, snapshots, logs, exports, backups e dados de treino sem inventar prazos legais.
- Ator/dados: instituição, equipe MIRA, Student.raw_data, TrainingEvent.features_snapshot, InterventionLog e audit events.
- Aceite: inventário por categoria com finalidade, acesso, retenção, expurgo e evidência de execução; teste de exportação/exclusão em staging.
- Evidência: backend/app/models/student.py, backend/app/models/tenant.py, backend/app/models/intervention.py, docs/AGENTES.md. Risco P1; revisão jurídica/contratual pendente.

## RB-PRI-002 — Preferências de comunicação são auditáveis
- Decisão APROVADA; implementação IMPLEMENTADA — EVIDÊNCIA ENCONTRADA para eventos de preferência; validação TESTADA PARCIALMENTE.
- Norma: mudanças explícitas de opt-out/preferências devem registrar origem, método, momento e valores anteriores/novos; dado ausente não revoga preferência existente.
- Evidência: backend/app/models/consent.py, backend/app/services/consent.py, backend/app/models/student.py, tests test_consent_governance.py/test_consent_topic_rules.py.
- Risco P0 para contato indevido; retenção dos eventos e tratamento de solicitações de titulares precisam de decisão.

## RB-PRI-003 — Uso em treino tem finalidade e autorização comprováveis
- Decisão APROVADA; implementação PARCIALMENTE IMPLEMENTADA; validação TESTADA PARCIALMENTE.
- Evidência: backend/app/models/data_governance.py, institutional_training_authorization.py e services/training_policy.py. Risco P0; tratamento de modelos já treinados após revogação pendente.
