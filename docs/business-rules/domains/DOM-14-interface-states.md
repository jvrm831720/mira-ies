# DOM-14 — Interface, estados e consistência da experiência

## RB-UX-001 — Interface reflete o resultado confirmado pelo backend
- Decisão APROVADA (prompt fundador); implementação NÃO VERIFICADA globalmente; validação NÃO TESTADA.
- Norma: loading, vazio, erro, sucesso e parcial são distintos; UI não afirma sucesso antes de confirmação do backend.
- Ator/dados: telas de importação, trabalho, alunos, retenção, membros e Control Center; respostas API e estados de job.
- Aceite: simular timeout, 4xx/5xx e resposta parcial; nenhuma mensagem de sucesso enganosa; erro de recurso alheio não revela dados.
- Evidência inicial: frontend/src/app/(app)/*, frontend/src/lib/api.ts, frontend/src/app/api/*/route.ts. Auditoria visual completa não realizada. Risco P1.

## RB-UX-002 — Estado de canal não equivale a conectividade
- Decisão APROVADA em docs de segurança; implementação IMPLEMENTADA — EVIDÊNCIA ENCONTRADA; validação TESTADA PARCIALMENTE.
- Norma: UI deve dizer “configurado” quando só verifica presença de credenciais; não declarar fornecedor operacional sem health check.
- Evidência: backend/app/api/control_center_admin.py, função _channel_status; docs/CONTROL_CENTER_SECURITY_REVIEW.md. Risco P2.
