# DOM-03 — Autenticação e sessões

## RB-AUT-001 — Identidade interna separada
- Decisão APROVADA; implementação IMPLEMENTADA — EVIDÊNCIA ENCONTRADA; validação TESTADA PARCIALMENTE.
- Norma: Control Center exige AdminPrincipal e sessão própria; conta institucional/API key de tenant não substitui identidade interna.
- Fluxo: senha válida → MFA por e-mail → sessão. Docs registram código de seis dígitos, validade de 5 min, uso único, até 5 tentativas, cooldown de 60s e rate limit por conta via Redis; Redis indisponível deve falhar fechado.
- Aceite: negar sem MFA, código expirado/reutilizado, excesso de tentativas, Redis/e-mail indisponível e token de cliente em rota admin.
- Evidência: backend/app/models/control_center.py, backend/app/api/control_center_auth.py, docs/CONTROL_CENTER_INTERNAL_AUTH.md, backend/tests/test_control_center_auth.py. Risco P0; concorrência MFA e staging hospedado pendentes.

## RB-AUT-002 — Sessão comum revogável
- Decisão APROVADA; implementação PARCIALMENTE IMPLEMENTADA; validação TESTADA PARCIALMENTE.
- Norma: sessões expiram; reset de senha e alterações críticas invalidam tokens antigos por auth_version.
- Evidência: backend/app/models/auth.py, docs/AUTH.md, backend/tests/test_mira_auth.py. Aceite: token com versão antiga é rejeitado. Verificar todos os caminhos e staging.

## RB-AUT-003 — Recuperação sem enumeração
- Decisão APROVADA; implementação PARCIALMENTE IMPLEMENTADA; validação TESTADA PARCIALMENTE.
- Norma: recuperação não revela existência da conta; tokens são hasheados, expiram e são consumidos.
- Evidência: backend/app/models/auth.py, docs/AUTH.md, backend/tests/test_auth_api.py. Risco P1; concorrência e bloqueio/desbloqueio pendentes.
