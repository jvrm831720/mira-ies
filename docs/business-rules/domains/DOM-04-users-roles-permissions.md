# DOM-04 — Usuários, perfis e permissões

## RB-RBAC-001 — Backend impõe permissão por ação/recurso
- Decisão APROVADA; implementação PARCIALMENTE IMPLEMENTADA; validação TESTADA PARCIALMENTE.
- Norma: cada rota protegida valida identidade, permissão e escopo; esconder botão não é controle de segurança.
- Fluxo: autenticar → autorizar ação → validar escopo → executar → auditar ação crítica. Negação não deve ser contornável por chamada direta.
- Aceite: matriz papel×endpoint com testes positivos/negativos; IDs de outro tenant não alteram estado.
- Evidência: backend/app/api/control_center_admin.py, backend/app/api/control_center_auth.py, backend/app/models/auth.py, tests test_control_center_auth.py e test_mira_admin_governance.py. Risco P0; matriz integral pendente.

## RB-RBAC-002 — Mudança de papel/status revoga sessão
- Decisão APROVADA; implementação IMPLEMENTADA — EVIDÊNCIA ENCONTRADA no endpoint administrativo observado; validação TESTADA PARCIALMENTE.
- Norma: mudança de papel/status incrementa auth_version; tokens anteriores devem falhar.
- Evidência: backend/app/api/control_center_admin.py, função update_member. Pendência: conferir caminhos alternativos e scripts.

## RB-RBAC-003 — Segregação para ações críticas
- Decisão RECOMENDAÇÃO; implementação NÃO VERIFICADA; validação NÃO TESTADA.
- Proposta: reautenticação e possível segunda aprovação para alteração de privilégios, recuperação MFA e ações destrutivas.
- Evidência: docs/MIRA_CONTROL_CENTER.md e docs/CONTROL_CENTER_INTERNAL_AUTH.md. Pendente: fundador aprovar ações sujeitas a dupla aprovação.
