# DOM-05 — Governança e auditoria

## RB-AUD-001 — Auditoria de ações críticas
- Decisão APROVADA; implementação PARCIALMENTE IMPLEMENTADA; validação TESTADA PARCIALMENTE.
- Norma: mudanças sensíveis registram ator, ação, alvo, resultado, timestamp, request ID e motivo quando aplicável; segredos e conteúdo pessoal desnecessário não entram em logs.
- Dados: AdminAuditEvent, ConsentAuditEvent. Efeito: evento e mutação devem ser persistidos consistentemente; acesso aos eventos é restrito.
- Aceite: mutações de instituição/membro/financeiro geram evento minimizado; logs sem senha, OTP, token ou mensagem integral.
- Evidência: backend/app/models/control_center.py, backend/app/models/consent.py, backend/app/api/control_center_admin.py, docs/CONTROL_CENTER_SECURITY_REVIEW.md. Risco P1; retenção, append-only técnico e atomicidade pendentes.

## RB-AUD-002 — Falhas investigáveis sem vazamento
- Decisão APROVADA; implementação PARCIALMENTE IMPLEMENTADA; validação TESTADA PARCIALMENTE.
- Norma: falhas de autenticação, acesso negado e incidentes relevantes têm telemetria minimizada e correlacionável.
- Aceite: eventos não contêm segredos; acesso não autorizado à auditoria é negado.
- Evidência: backend/app/api/control_center_auth.py e docs/CONTROL_CENTER_SECURITY_REVIEW.md. Cobertura de todas as rotas pendente.

## RB-AUD-003 — Evidência de autorização de treino
- Decisão APROVADA; implementação PARCIALMENTE IMPLEMENTADA; validação TESTADA PARCIALMENTE.
- Norma: uso para treino deve referenciar autorização, versão contratual, aprovador e elegibilidade aplicável.
- Evidência: backend/app/models/data_governance.py e institutional_training_authorization.py. Risco P0; auditoria persistente de cada decisão do pipeline pendente.
